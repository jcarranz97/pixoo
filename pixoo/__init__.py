import base64
from enum import IntEnum

from PIL import Image, ImageOps

from ._colors import Palette
from ._font import retrieve_glyph
from .simulator import Simulator, SimulatorConfig
from pixoo.find_device import get_pixoo_devices as _get_pixoo_devices
import pixoo.exceptions as _exceptions
from pixoo.api import PixooBaseApi
from pixoo.tools import ScoreBoard, StopWatch


def clamp(value, minimum=0, maximum=255):
    if value > maximum:
        return maximum
    if value < minimum:
        return minimum

    return value


def clamp_color(rgb):
    return clamp(rgb[0]), clamp(rgb[1]), clamp(rgb[2])


def lerp(start, end, interpolant):
    return start + interpolant * (end - start)


def lerp_location(xy1, xy2, interpolant):
    return lerp(xy1[0], xy2[0], interpolant), lerp(xy1[1], xy2[1], interpolant)


def minimum_amount_of_steps(xy1, xy2):
    return max(abs(xy1[0] - xy2[0]), abs(xy1[1] - xy2[1]))


def rgb_to_hex_color(rgb):
    return f'#{rgb[0]:0>2X}{rgb[1]:0>2X}{rgb[2]:0>2X}'


def round_location(xy):
    return round(xy[0]), round(xy[1])


class Channel(IntEnum):
    FACES = 0
    CLOUD = 1
    VISUALIZER = 2
    CUSTOM = 3


class ImageResampleMode(IntEnum):
    PIXEL_ART = Image.NEAREST
    SMOOTH = Image.ANTIALIAS


class TextScrollDirection(IntEnum):
    LEFT = 0
    RIGHT = 1


class Pixoo(PixooBaseApi):
    __buffer = []
    __buffers_send = 0
    __counter = 0
    __refresh_counter_limit = 32
    __simulator = None

    def __init__(self, address=None, size=64, debug=False, refresh_connection_automatically=True, simulated=False,
                 simulation_config=SimulatorConfig()):
        assert size in [16, 32, 64], \
            'Invalid screen size in pixels given. ' \
            'Valid options are 16, 32, and 64'

        self.refresh_connection_automatically = refresh_connection_automatically
        if address is None:
            self.__address = self.__get_first_pixoo_device_address()
        else:
            self.__address = address
        super().__init__(self.__address)
        self.debug = debug
        self.size = size
        self.simulated = simulated

        # Total number of pixels
        self.pixel_count = self.size * self.size

        # Generate URL
        self.__url = 'http://{0}/post'.format(self.address)

        # Prefill the buffer
        self.fill()

        # Retrieve the counter
        self.__load_counter()

        # Resetting if needed
        if self.refresh_connection_automatically and self.__counter > self.__refresh_counter_limit:
            self.__reset_counter()

        # We're going to need a simulator
        if self.simulated:
            self.__simulator = Simulator(self, simulation_config)

    @staticmethod
    def __get_first_pixoo_device_address():
        pixoo_devices = _get_pixoo_devices()
        if len(pixoo_devices) > 1:
            raise _exceptions.MoreThanOnePixooFound(f"PixoDevices: {pixoo_devices}")
        pixoo_device = pixoo_devices[0]  # Just take first (and unique) item
        dev_name = pixoo_device["DeviceName"]
        dev_ip = pixoo_device["DevicePrivateIP"]
        print(f" Pixo Device auto identified!!! DeviceName: {dev_name} (IP: {dev_ip})")
        return dev_ip

    def clear(self, rgb=Palette.BLACK):
        self.fill(rgb)

    def clear_rgb(self, r, g, b):
        self.fill_rgb(r, g, b)

    def draw_character(self, character, xy=(0, 0), rgb=Palette.WHITE):
        matrix = retrieve_glyph(character)
        if matrix is not None:
            for index, bit in enumerate(matrix):
                if bit == 1:
                    local_x = index % 3
                    local_y = int(index / 3)
                    self.draw_pixel((xy[0] + local_x, xy[1] + local_y), rgb)

    def draw_character_at_location_rgb(self, character, x=0, y=0, r=255, g=255,
                                       b=255):
        self.draw_character(character, (x, y), (r, g, b))

    def draw_filled_rectangle(self, top_left_xy=(0, 0), bottom_right_xy=(1, 1),
                              rgb=Palette.BLACK):
        for y in range(top_left_xy[1], bottom_right_xy[1] + 1):
            for x in range(top_left_xy[0], bottom_right_xy[0] + 1):
                self.draw_pixel((x, y), rgb)

    def draw_filled_rectangle_from_top_left_to_bottom_right_rgb(self,
                                                                top_left_x=0,
                                                                top_left_y=0,
                                                                bottom_right_x=1,
                                                                bottom_right_y=1,
                                                                r=0, g=0, b=0):
        self.draw_filled_rectangle((top_left_x, top_left_y),
                                   (bottom_right_x, bottom_right_y), (r, g, b))

    def draw_image(self, image_path_or_object, xy=(0, 0),
                   image_resample_mode=ImageResampleMode.PIXEL_ART,
                   pad_resample=False):
        image = image_path_or_object if isinstance(image_path_or_object,
                                                   Image.Image) else Image.open(
            image_path_or_object)
        size = image.size
        width = size[0]
        height = size[1]

        # See if it needs to be scaled/resized to fit the display
        if width > self.size or height > self.size:
            if pad_resample:
                image = ImageOps.pad(image, (self.size, self.size),
                                     image_resample_mode)
            else:
                image.thumbnail((self.size, self.size), image_resample_mode)

            if self.debug:
                print(
                    f'[.] Resized image to fit on screen (saving aspect ratio): "{image_path_or_object}" ({width}, {height}) '
                    f'-> ({image.size[0]}, {image.size[1]})')

        # Convert the loaded image to RGB
        rgb_image = image.convert('RGB')

        # Iterate over all pixels in the image that are left and buffer them
        for y in range(image.size[1]):
            for x in range(image.size[0]):
                location = (x, y)
                placed_x = x + xy[0]
                if self.size - 1 < placed_x or placed_x < 0:
                    continue

                placed_y = y + xy[1]
                if self.size - 1 < placed_y or placed_y < 0:
                    continue

                self.draw_pixel((placed_x, placed_y),
                                rgb_image.getpixel(location))

    def draw_image_at_location(self, image_path_or_object, x, y,
                               image_resample_mode=ImageResampleMode.PIXEL_ART):
        self.draw_image(image_path_or_object, (x, y), image_resample_mode)

    def draw_line(self, start_xy, stop_xy, rgb=Palette.WHITE):
        line = set()

        # Calculate the amount of steps needed between the points to draw a nice line
        amount_of_steps = minimum_amount_of_steps(start_xy, stop_xy)

        # Iterate over them and create a nice set of pixels
        for step in range(amount_of_steps):
            if amount_of_steps == 0:
                interpolant = 0
            else:
                interpolant = step / amount_of_steps

            # Add a pixel as a rounded location
            line.add(
                round_location(lerp_location(start_xy, stop_xy, interpolant)))

        # Draw the actual pixel line
        for pixel in line:
            self.draw_pixel(pixel, rgb)

    def draw_line_from_start_to_stop_rgb(self, start_x, start_y, stop_x, stop_y,
                                         r=255, g=255, b=255):
        self.draw_line((start_x, start_y), (stop_x, stop_y), (r, g, b))

    def draw_pixel(self, xy, rgb):
        # If it's not on the screen, we're not going to bother
        if xy[0] < 0 or xy[0] >= self.size or xy[1] < 0 or xy[1] >= self.size:
            if self.debug:
                limit = self.size - 1
                print(
                    f'[!] Invalid coordinates given: ({xy[0]}, {xy[1]}) (maximum coordinates are ({limit}, {limit})')
            return

        # Calculate the index
        index = xy[0] + (xy[1] * self.size)

        # Color it
        self.draw_pixel_at_index(index, rgb)

    def draw_pixel_at_index(self, index, rgb):
        # Validate the index
        if index < 0 or index >= self.pixel_count:
            if self.debug:
                print(f'[!] Invalid index given: {index} (maximum index is {self.pixel_count - 1})')
            return

        # Clamp the color, just to be safe
        rgb = clamp_color(rgb)

        # Move to place in array
        index = index * 3

        self.__buffer[index] = rgb[0]
        self.__buffer[index + 1] = rgb[1]
        self.__buffer[index + 2] = rgb[2]

    def draw_pixel_at_index_rgb(self, index, r, g, b):
        self.draw_pixel_at_index(index, (r, g, b))

    def draw_pixel_at_location_rgb(self, x, y, r, g, b):
        self.draw_pixel((x, y), (r, g, b))

    def draw_text(self, text, xy=(0, 0), rgb=Palette.WHITE):
        for index, character in enumerate(text):
            self.draw_character(character, (index * 4 + xy[0], xy[1]), rgb)

    def draw_text_at_location_rgb(self, text, x, y, r, g, b):
        self.draw_text(text, (x, y), (r, g, b))

    def fill(self, rgb=Palette.BLACK):
        self.__buffer = []
        rgb = clamp_color(rgb)
        for index in range(self.pixel_count):
            self.__buffer.extend(rgb)

    def fill_rgb(self, r, g, b):
        self.fill((r, g, b))

    def push(self):
        self.__send_buffer()

    def send_text(self, text, xy=(0, 0), color=Palette.WHITE, identifier=1,
                  font=2, width=64,
                  movement_speed=0,
                  direction=TextScrollDirection.LEFT):

        # This won't be possible
        if self.simulated:
            return

        # Make sure the identifier is valid
        identifier = clamp(identifier, 0, 19)
        self.send_command(
            command="Draw/SendText",
            text_id=identifier,
            x=xy[0],
            y=xy[1],
            dir=direction,
            font=font,
            text_width=width,
            speed=movement_speed,
            text_string=text,
            color=rgb_to_hex_color(color),
            align=1,  # Align text was not previously defined, so assuming 1
        )

    def set_brightness(self, brightness):
        # This won't be possible
        if self.simulated:
            return

        brightness = clamp(brightness, 0, 100)
        self.send_command(
            command="Channel/SetBrightness",
            brightness=brightness,
        )

    def set_channel(self, channel):
        # This won't be possible
        if self.simulated:
            return

        self.send_command(
            command="Channel/SetIndex",
            select_index=channel,
        )

    def set_clock(self, clock_id):
        # This won't be possible
        if self.simulated:
            return

        self.send_command(
            command="Channel/SetClockSelectId",
            clock_id=clock_id,
        )

    def set_custom_channel(self, index):
        self.set_custom_page(index)
        self.set_channel(3)

    def set_custom_page(self, index):
        self.send_command(
            command="Channel/SetCustomPageIndex",
            custom_page_index=index,
        )

    def set_face(self, face_id):
        self.set_clock(face_id)

    def set_screen(self, on=True):
        # This won't be possible
        if self.simulated:
            return

        self.send_command(
            command="Channel/OnOffScreen",
            on_off=1 if on else 0,
        )

    def set_screen_off(self):
        self.set_screen(False)

    def set_screen_on(self):
        self.set_screen(True)

    def set_visualizer(self, equalizer_position):
        # This won't be possible
        if self.simulated:
            return

        self.send_command(
            command="Channel/SetEqPosition",
            eq_position=equalizer_position,
        )

    def __clamp_location(self, xy):
        return clamp(xy[0], 0, self.size - 1), clamp(xy[1], 0, self.size - 1)

    def __error(self, error):
        if self.debug:
            print('[x] Error on request ' + str(self.__counter))
            print(error)

    def __load_counter(self):
        # Just assume it's starting at the beginning if we're simulating
        if self.simulated:
            self.__counter = 1
            return

        data = self.send_command(command="Draw/GetHttpGifId")
        self.__counter = int(data['PicId'])
        if self.debug:
            print('[.] Counter loaded and stored: ' + str(self.__counter))

    def __send_buffer(self):

        # Add to the internal counter
        self.__counter = self.__counter + 1

        # Check if we've passed the limit and reset the counter for the animation remotely
        if self.refresh_connection_automatically and self.__counter >= self.__refresh_counter_limit:
            self.__reset_counter()
            self.__counter = 1

        if self.debug:
            print(f'[.] Counter set to {self.__counter}')

        # If it's simulated, we don't need to actually push it to the divoom
        if self.simulated:
            self.__simulator.display(self.__buffer, self.__counter)

            # Simulate this too I suppose
            self.__buffers_send = self.__buffers_send + 1
            return

        # Encode the buffer to base64 encoding
        self.send_command(
            command="Draw/SendHttpGif",
            pic_num=1,
            pic_width=self.size,
            pic_offset=0,
            pic_id=self.__counter,
            pic_speed=1000,
            pic_data=str(base64.b64encode(bytearray(self.__buffer)).decode()),
        )
        self.__buffers_send = self.__buffers_send + 1

        if self.debug:
            print(f'[.] Pushed {self.__buffers_send} buffers')

    def __reset_counter(self):
        if self.debug:
            print('[.] Resetting counter remotely')

        # This won't be possible
        if self.simulated:
            return

        self.send_command(
            command="Draw/ResetHttpGifId",
        )

    @property
    def url(self):
        """ Get device URL """
        return self.__url

    @property
    def address(self):
        """ Get device address """
        return self.__address

    @property
    def buffer(self):
        """ Get buffer of device """
        return self.__buffer

    def set_timer(self, minutes: int, seconds: int, start_counter: bool = True):
        """ Start countdown timer in divoom device

        Arguments:
            - minutes: Minutes to countdown.
            - seconds: Seconds to countdown.
            - start_counter: If true, counter will start counting down immediately.

        """
        # API: http://docin.divoom-gz.com/web/#/5/50
        self.send_command(
            command="Tools/SetTimer",
            minute=minutes,
            second=seconds,
            status=int(start_counter),  # Always enable timer
        )

    def get_score_board(self):
        """ Get score board object """
        return ScoreBoard(self.address)

    def get_stop_watch(self):
        """ Get stop watch object """
        return StopWatch(self.address)


__all__ = (Channel, ImageResampleMode, Pixoo, TextScrollDirection)

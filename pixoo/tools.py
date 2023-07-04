""" Classes for in-device tools like timer, stopwatch, scoreboard, etc """
from pixoo.api import PixooBaseApi


class ScoreBoard(PixooBaseApi):
    """ Scoreboard tool """
    def __init__(self, address=None, start_scores=(0, 0)):
        super().__init__(address)
        self.__blue_score = start_scores[0]
        self.__red_score = start_scores[1]
        self.set_scores(
            blue_score=self.__blue_score,
            red_score=self.__red_score,
        )

    def set_scores(self, blue_score=0, red_score=0):
        """ Send score to Pixoo board """
        self.__blue_score = blue_score
        self.__red_score = red_score
        self.send_command(
            command="Tools/SetScoreBoard",
            blue_score=blue_score,
            red_score=red_score,
        )

    @property
    def blue_score(self):
        """ Blue team score """
        return self.__blue_score

    @blue_score.setter
    def blue_score(self, value):
        self.__blue_score = value
        self.set_scores(
            blue_score=self.__blue_score,
            red_score=self.__red_score,
        )

    @property
    def red_score(self):
        """ Red team score """
        return self.__red_score

    @red_score.setter
    def red_score(self, value):
        self.__red_score = value
        self.set_scores(
            blue_score=self.__blue_score,
            red_score=self.__red_score,
        )


class StopWatch(PixooBaseApi):
    """ Stopwatch tool """
    def __init__(self, address=None):
        super().__init__(address)
        self.reset_counter()

    def reset_counter(self):
        """ Reset stopwatch counter """
        self.send_command(
            command="Tools/SetStopWatch",
            status=2,  # Reset
        )

    def start_counter(self):
        """ Start stopwatch counter """
        self.send_command(
            command="Tools/SetStopWatch",
            status=1,  # Start
        )

    def stop_counter(self):
        """ Stop stopwatch counter """
        self.send_command(
            command="Tools/SetStopWatch",
            status=0,  # Stop
        )

import random
import time

from rlbot.agents.base_agent import BaseAgent, SimpleControllerState
from rlbot.messages.flat.QuickChatSelection import QuickChatSelection
from rlbot.utils.structures.game_data_struct import GameTickPacket

from util.ball_prediction_analysis import find_slice_at_time
from util.boost_pad_tracker import BoostPadTracker
from util.drive import steer_toward_target
from util.sequence import Sequence, ControlStep
from util.vec import Vec3
from util.orientation import Orientation

class BoostHog(BaseAgent):

    def __init__(self, name, team, index):
        super().__init__(name, team, index)
        self.active_sequence: Sequence = None
        self.boost_pad_tracker = BoostPadTracker()
        self.boost: bool = False
        self.counter = 0  # Track time in ticks (or update intervals)
        self.delay = 100  # Delay after 100 ticks (can adjust as needed)


    def initialize_agent(self):
        # Set up information about the boost pads now that the game is active and the info is available
        # Runs once before bot starts up
        self.boost_pad_tracker.initialize_boosts(self.get_field_info())

    def get_output(self, packet: GameTickPacket) -> SimpleControllerState:
        """
        This function will be called by the framework many times per second. This is where you can
        see the motion of the ball, etc. and return controls to drive your car.
        """

        # Keep our boost pad info updated with which pads are currently active
        self.boost_pad_tracker.update_boost_status(packet)

        # This is good to keep at the beginning of get_output. It will allow you to continue
        # any sequences that you may have started during a previous call to get_output.
        if self.active_sequence is not None and not self.active_sequence.done:
            controls = self.active_sequence.tick(packet)
            if controls is not None:
                return controls

        # Gather some information about our car and the ball
        my_car = packet.game_cars[self.index]
        info = self.get_field_info()
        car_location = Vec3(my_car.physics.location)
        nearest_boost_loc = self.get_nearest_boost(info, packet, car_location)
        car_velocity = Vec3(my_car.physics.velocity)
        ball_location = Vec3(packet.game_ball.physics.location)
        corner_debug = "Time Remaining: {}\n".format(packet.game_info.game_time_remaining)
        corner_debug += "First boost location: {}\n".format(info.boost_pads[0].location)
        corner_debug += "Nearest boost location: {}\n".format(nearest_boost_loc)
        target_location = nearest_boost_loc
        corner_debug += "Target location: {}\n".format(target_location)
        boost_amount = my_car.boost

        if boost_amount > 20:
            if car_location.dist(nearest_boost_loc) > 1500:
                target_location = ball_location

                # We're far away from the ball, let's try to lead it a little bit
                ball_prediction = self.get_ball_prediction_struct()  # This can predict bounces, etc
                ball_in_future = find_slice_at_time(ball_prediction, packet.game_info.seconds_elapsed + 2)

                # ball_in_future might be None if we don't have an adequate ball prediction right now, like during
                # replays, so check it to avoid errors.
                target_location = Vec3(ball_in_future.physics.location)
                if ball_in_future is not None:
                    self.renderer.draw_line_3d(ball_location, target_location, self.renderer.cyan())
            target_location = nearest_boost_loc
        else:
            target_location = nearest_boost_loc

        # Draw some things to help understand what the bot is thinking
        self.renderer.draw_line_3d(car_location, target_location, self.renderer.white())
        self.renderer.draw_line_3d(car_location, nearest_boost_loc, self.renderer.yellow())
        self.renderer.draw_string_3d(car_location, 1, 1, f'Speed: {car_velocity.length():.1f}', self.renderer.white())
        if corner_debug:
            corner_display_y = 900 - (corner_debug.count('\n') * 20)
            self.renderer.draw_string_2d(10, corner_display_y, 1, 1, corner_debug, self.renderer.white())
        self.renderer.draw_rect_3d(target_location, 8, 8, True, self.renderer.cyan(), centered=True)
        self.renderer.draw_rect_3d(nearest_boost_loc, 8, 8, True, self.renderer.white(), centered=True)

        if 750 < car_velocity.length() < 800:
            # We'll do a front flip if the car is moving at a certain speed.
            return self.begin_front_flip(packet)

        controls = SimpleControllerState()
        controls.steer = steer_toward_target(my_car, target_location)
        controls.throttle = 1.0
        self.counter += 1
        if boost_amount > 20:
            controls.boost = True
        else:
            controls.boost = False
        # You can set more controls if you want, like controls.boost.

        return controls

    def begin_front_flip(self, packet):
        # Send some quickchat just for fun
        self.send_quick_chat(team_only=False, quick_chat=QuickChatSelection.Information_IGotIt)

        # Do a front flip. We will be committed to this for a few seconds and the bot will ignore other
        # logic during that time because we are setting the active_sequence.
        self.active_sequence = Sequence([
            ControlStep(duration=0.05, controls=SimpleControllerState(jump=True)),
            ControlStep(duration=0.05, controls=SimpleControllerState(jump=False)),
            ControlStep(duration=0.2, controls=SimpleControllerState(jump=True, pitch=-1)),
            ControlStep(duration=0.8, controls=SimpleControllerState()),
        ])

        # Return the controls associated with the beginning of the sequence so we can start right away.
        return self.active_sequence.tick(packet)

    def get_nearest_boost(self, info, packet, car_location):
        nearest_boost_loc = None

        # loop over all boosts
        for i, boost in enumerate(info.boost_pads):
            # only want large boosts that haven't been taken
            if boost.is_full_boost and packet.game_boosts[i].is_active:

                if not nearest_boost_loc:
                    nearest_boost_loc = boost.location
                else:
                    # if this boost is closer, save that
                    if car_location.dist(Vec3(boost.location)) < car_location.dist(Vec3(nearest_boost_loc)):
                        nearest_boost_loc = boost.location

        return nearest_boost_loc


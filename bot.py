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
        self.chase_ball_game_time = 0
        self.boosts_counted = False
        self.active_sequence: Sequence = None
        self.boost_pad_tracker = BoostPadTracker()
        self.boost: bool = False
        self.counter = 0  # Track time in ticks (or update intervals)
        self.delay = 100  # Delay after 100 ticks (can adjust as needed)
        self.has_kickoff_happened = False
        self.boosts_collected = 0


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
        target_location = nearest_boost_loc
        behavior_mode = "Unknown"
        boost_amount = my_car.boost
        controls = SimpleControllerState()

        controls = self.action_goto(my_car, target_location, packet, controls, boost_amount, car_velocity, nearest_boost_loc, ball_location)

        if not self.has_kickoff_happened:
            behavior_mode = "Chasing ball"
        elif packet.game_info.game_time_remaining > self.chase_ball_game_time - 5:
            pass
        else:
            behavior_mode = "Getting boost"

        if packet.game_info.is_kickoff_pause:
            self.has_kickoff_happened = False

        # update boosts collected
        self.update_boosts_collected(my_car, packet)

        if target_location is None:
            target_location = ball_location

        corner_debug = "Time Elapsed: {}\n".format(packet.game_info.game_time_remaining * -2 + packet.game_info.game_time_remaining)
        corner_debug += "Boosts collected: {}\n".format(self.boosts_collected)
        corner_debug += "Target location: {}\n".format(target_location)
        corner_debug += "Kickoff happened: {}\n".format(self.has_kickoff_happened)
        corner_debug += "Ball location: {}\n".format(ball_location.flat())
        corner_debug += "Behavior mode {}\n".format(behavior_mode)

        # Draw some things to help understand what the bot is thinking
        self.renderer.draw_line_3d(car_location, ball_location, self.renderer.white())
        if nearest_boost_loc is not None:
            self.renderer.draw_line_3d(car_location, nearest_boost_loc, self.renderer.yellow())
            self.renderer.draw_rect_3d(nearest_boost_loc, 8, 8, True, self.renderer.white(), centered=True)
        self.renderer.draw_string_3d(car_location, 1, 1, f'Speed: {car_velocity.length():.1f}', self.renderer.white())
        if corner_debug:
            corner_display_y = 900 - (corner_debug.count('\n') * 20)
            self.renderer.draw_string_2d(10, corner_display_y, 1, 1, corner_debug, self.renderer.white())
        if target_location is not None:
            self.renderer.draw_rect_3d(target_location, 8, 8, True, self.renderer.cyan(), centered=True)


        return controls

    def action_goto(self, my_car, target_location, packet, controls, boost_amount, car_velocity, nearest_boost_loc, ball_location):
        field_center = Vec3(0, 0, 0)

        if target_location is None:
            controls.steer = steer_toward_target(my_car, field_center)
            controls.throttle = 1.0
            self.counter += 1
            controls.boost = boost_amount > 20
            return controls

        # if boost_amount > 20:
            # if car_location.dist(target_location) > 1500:
                # We're far away from the ball, try to lead it a little
                # ball_prediction = self.get_ball_prediction_struct()
                # ball_in_future = find_slice_at_time(ball_prediction, packet.game_info.seconds_elapsed + 2)

                # if ball_in_future is not None:
                    # target_location = Vec3(ball_in_future.physics.location)
                    # self.renderer.draw_line_3d(ball_location, target_location, self.renderer.cyan())
                # else:
                    # target_location = ball_location
            # else:
                # target_location = nearest_boost_loc  # Optional: could be skipped

        if 750 < car_velocity.length() < 800:
            return begin_front_flip(self, packet)

        if not self.has_kickoff_happened:
            target_location = ball_location
            if ball_location.flat() != Vec3(0, 0,0):
                self.has_kickoff_happened = True
        else:
            target_location = nearest_boost_loc

        # if self.boosts_collected >= 25:
            # target_location = ball_location

        controls.steer = steer_toward_target(my_car, target_location)
        controls.throttle = 1.0

        controls.boost = boost_amount > 20

        return controls

    def update_boosts_collected(self, my_car, packet):
        # mark when 25 boosts have been reached
        if my_car.boost >= 100:
            if not self.boosts_counted:
                self.boosts_collected += 1
            self.boosts_counted = True
        else:
            self.boosts_counted = False

        if self.boosts_collected > 5:
            self.chase_ball_game_time = packet.game_info.game_time_remaining
            self.boosts_collected = 0


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
        if nearest_boost_loc is None:
            for i, boost in enumerate(info.boost_pads):
                # only want large boosts that haven't been taken
                if packet.game_boosts[i].is_active:
                    if not nearest_boost_loc:
                        nearest_boost_loc = boost.location
                    else:
                        # if this boost is closer, save that
                        if car_location.dist(Vec3(boost.location)) < car_location.dist(Vec3(nearest_boost_loc)):
                            nearest_boost_loc = boost.location
        return nearest_boost_loc


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


#include "move_action-node.hpp"
#include <memory>


using namespace std::placeholders;

moveAction::moveAction() : ActionExecutorClient("move",250ms) {

    zone_client_ = create_client<GetZone>("/world_model_server/get_zone");
    move_client_ = rclcpp_action::create_client<RobotMove>(this, "/arm_1/niryo_robot_arm_commander/robot_action");
    alert_sub_ = create_subscription<SafetyAlert>("/safety_alert", 10, bind(&moveAction::on_alert, this, _1));
    //command_sent_ = false;

    declare_parameter("wait_timeout",3.0);
    wait_timeout_ = get_parameter("wait_timeout").as_double();

    state_ = State::IDLE;
    goal_seq_ = 0;
}

void moveAction::do_work(){

    if (state_ == State::IDLE) {
        auto args = get_arguments();
        from_ = args[1];
        to_ = args[2];

        target_ = from_ + "->" + to_;
        state_ = State::MOVING;
        dispatch_move(to_);
        send_feedback(0.0, "Requesting zone info");
        return;
    }

    if (state_ == State::WAITING){

        //Micro-wait expired with the obstacle still there: give up on ?to and
        //go back to ?from. The failure is issued later, from RETURNING's result.
        if ((now() - wait_start_).seconds() > wait_timeout_){
            RCLCPP_WARN(get_logger(),
                "Obstacle on '%s' persists: returning to '%s'", target_.c_str(), from_.c_str());
            state_ = State::RETURNING;
            dispatch_move(from_);
        }

        return;
    }
}

void moveAction::dispatch_move(const string& zone)
{
    auto request = std::make_shared<GetZone::Request>();

    request->zone = zone;
    zone_client_ -> async_send_request(
        request,
        [this, zone](rclcpp::Client<GetZone>::SharedFuture future){
            auto response = future.get();
            if (!response->success){
                RCLCPP_ERROR(get_logger(), "Failed to get zone info for '%s'", zone.c_str());
                state_ = State::IDLE;
                finish(false, 0.0, "Zone not found");
                return;
            }
            send_move_command(response);
        });
}

void moveAction::send_move_command(GetZone::Response::SharedPtr response){

    niryo_ned_ros2_interfaces::msg::ArmMoveCommand cmd;

    cmd.cmd_type = niryo_ned_ros2_interfaces::msg::ArmMoveCommand::POSE;
    cmd.position = response->position;
    cmd.rpy = response->rpy;

    auto goal = RobotMove::Goal();
    goal.cmd = cmd;

    // Each dispatch gets a fresh sequence number. Both callbacks capture it and
    // ignore anything that arrives for a goal we have since superseded (e.g. an
    // old goal completed after we already re-dispatched).
    const uint64_t seq_num = ++goal_seq_;

    auto goal_opt = rclcpp_action::Client<RobotMove>::SendGoalOptions();

    goal_opt.goal_response_callback = [this, seq_num](GoalHandleRobotMove::SharedPtr handle){

        if (seq_num != goal_seq_)
            return;

        if (!handle){
            RCLCPP_ERROR(get_logger(), "Move goal rejected by the driver");
            state_ = State::IDLE;
            finish(false, 0.0, "Goal_rejected");
            return;
        }
        goal_handle_ = handle;

        // Second half of the double-cancellation: an alert may have fired in the
        // blind window before the goal was accepted, when on_alert had no handle 
        // to cancel. Now that we hold one, cancel it here.
        if (state_ == State::WAITING){
            move_client_->async_cancel_goal(goal_handle_);
            RCLCPP_WARN(get_logger(), "Cancelling the goal that was accepted after the alert");
        }
    };

    goal_opt.result_callback = [this, seq_num](const GoalHandleRobotMove::WrappedResult& result){
        
        if (seq_num != goal_seq_)
            return;
        
        goal_handle_.reset();

        //Success either from the action result code or the driver's own status flag.
        const bool ok = (result.code == rclcpp_action::ResultCode::SUCCEEDED) || (result.result->status == 1);

        if (state_ == State::WAITING){
            // The move may have completed before our cancel tool effect; if so,
            // accept the completion rather than forcing a needless replan.
            if (ok){
                state_ = State::IDLE;
                finish(true, 1.0, "Move completed before the stop took effect");
            }
            return;
        }

        if (state_ == State::RETURNING){
            // Back at ?from after a persistent obstacle: fail on purpose
            // so POPF replans around the blocked arc. This is the reactive-replanning
            // trigger.
            state_ = State::IDLE;
            finish(false, 0.0, "Obstacle on " + target_ + ", arm back at " + from_);
            return;
        }

        state_ = State::IDLE;
        if (ok){
            RCLCPP_INFO(get_logger(), "Move action succeeded");
            finish(true, 1.0, "Move completed");
        }else{
            RCLCPP_ERROR(get_logger(), "Move action failed");
            finish(false, 0.0, "Move failed");
        }
    };

    move_client_->async_send_goal(goal, goal_opt);
    send_feedback(0.5, "Move command sent");
}

void moveAction::on_alert(const SafetyAlert::SharedPtr msg)
{
    if (msg->target != target_)
        return;

    if (msg->blocked && state_ == State::MOVING){
        RCLCPP_WARN(get_logger(), "obstacle on '%s': stopping", target_.c_str());
        state_ = State::WAITING;
        wait_start_ = now();

        // First half of the double-cancellation: cancel now if the goal is 
        // already accepted. If it is still in the blind window, goal_response_callback
        // cancels it once the handles arrives.

        if(goal_handle_){
            move_client_->async_cancel_goal(goal_handle_);
        }

        send_feedback(0.5, "Stopped: obstacle on " + target_);
        return;
    }

    if (!msg->blocked && state_ == State::WAITING){
        RCLCPP_INFO(get_logger(), "'%s' clear again: resuming", target_.c_str());
        state_ = State::MOVING;
        dispatch_move(to_);
        send_feedback(0.5, "Resume towards " + to_);
    }
}

int main(int argc, char ** argv)
{
    init(argc, argv);
    auto node = std::make_shared<moveAction>();

    node->set_parameter(rclcpp::Parameter("action_name", "move"));
    node->trigger_transition(lifecycle_msgs::msg::Transition::TRANSITION_CONFIGURE);
    spin(node->get_node_base_interface());
    shutdown();
    return 0;
}

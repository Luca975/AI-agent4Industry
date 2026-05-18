#include "move_action-node.hpp"
#include <memory>


using namespace std::placeholders;

moveAction::moveAction() : ActionExecutorClient("move",250ms) {
    zone_client_ = create_client<GetZone>("get_zone");
    move_client_ = rclcpp_action::create_client<RobotMove>(this, "/arm_1/niryo_robot_arm_commander/robot_action");

    command_sent_ = false;
}

void moveAction::do_work(){

    if (command_sent_) {
        return;
    }

    auto args=get_arguments();
    string to = args[2];

    auto request = std::make_shared<GetZone::Request>();
    request->zone = to;

    zone_client_->async_send_request(
       request,
       [this, to](rclcpp::Client<GetZone>::SharedFuture future) {
            auto response = future.get();
            RCLCPP_INFO(get_logger(), "Received zone info for zone %s", to.c_str());
            if(!response->success){
                RCLCPP_ERROR(get_logger(), "Failed to get zone info for zone %s", to.c_str());
                finish(false,0.0,"Zone not found");
                return;
            }
            send_move_command(response);
       });
    command_sent_ = true;
    send_feedback(0.0,"Requesting zone info");
}

void moveAction::send_move_command(GetZone::Response::SharedPtr response){

    niryo_ned_ros2_interfaces::msg::ArmMoveCommand cmd;

    cmd.cmd_type = niryo_ned_ros2_interfaces::msg::ArmMoveCommand::POSE;
    cmd.position = response->position;
    cmd.rpy = response->rpy;

    auto goal = RobotMove::Goal();
    goal.cmd = cmd;

    auto send_goal_opt = rclcpp_action::Client<RobotMove>::SendGoalOptions();
    send_goal_opt.result_callback = [this](const rclcpp_action::ClientGoalHandle<RobotMove>::WrappedResult & result){
        if(result.code == rclcpp_action::ResultCode::SUCCEEDED || result.result->status == 1){
            RCLCPP_INFO(get_logger(), "Move action succeeded");
            finish(true,1.0,"Move completed");
        } else {
            RCLCPP_ERROR(get_logger(), "Move action failed");
            finish(false,0.0,"Move failed");
        }
        command_sent_= false;
    };
    move_client_->async_send_goal(goal, send_goal_opt);
    send_feedback(0.5,"Move command sent");
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

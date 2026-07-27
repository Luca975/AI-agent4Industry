#include "pick_action-node.hpp"
#include <memory>

using namespace std::placeholders;

PickAction::PickAction() : ActionExecutorClient("pick",250ms)
{
    QoS qos(1);
    qos.transient_local();
    tool_status_pub_ = create_publisher<ToolStatus>(TOOL_STATUS_TOPIC, qos);

    alert_sub_ = create_subscription<SafetyAlert>("/safety_alert",10, 
                            bind(&PickAction::on_alert, this, _1));

    declare_parameter("work_duration", 5.0);
    declare_parameter("wait_timeout",3.0);
    work_duration_ = get_parameter("work_duration").as_double();
    wait_timeout_ = get_parameter("wait_timeout").as_double();

    state_ = State::IDLE;
}

CallbackReturnT PickAction::on_activate(const rclcpp_lifecycle::State& state)
{
    tool_status_pub_->on_activate();
    return ActionExecutorClient::on_activate(state);
}

void PickAction::do_work()
{
    if (state_ == State::IDLE){
        target_ = get_arguments()[1];

        state_ = State::WORKING;
        work_start_ = now();
        RCLCPP_INFO(get_logger(), "Picking at '%s'", target_.c_str());
        send_feedback(0.0, "Pick started");
        return;
    }

    if (state_ == State::WORKING){
        /*TODO: The real implementation commands the gripper through the tools_commander
        action and finishes on its result, not a timer*/
        const double elapsed = (now()-work_start_).seconds();

        if (elapsed >= work_duration_){
            publish_tool_status(true);
            state_ = State::IDLE;
            finish(true, 1.0, "Pick completed");
            return;
        }

        send_feedback(elapsed/work_duration_, "Picking");
    }

    if (state_ == State::WAITING){

        if ((now()-wait_start_).seconds() > wait_timeout_){
            RCLCPP_WARN(get_logger(), "Obstacle on '%s' persists: aborting the pick", target_.c_str());
            state_ = State::IDLE;
            finish(false, 0.0, "Obstacle on " + target_);
        }
        return;
    }
}

void PickAction::on_alert(const SafetyAlert::SharedPtr msg)
{
    if (msg->target != target_)
        return;
    
    if (msg->blocked && state_==State::WORKING){
        RCLCPP_WARN(get_logger(), "Obstacle on '%s': suspending the pick", target_.c_str());
        state_ = State::WAITING;
        wait_start_ = now();

        /*TODO: the real implementation cancel the gripper goal here*/

        send_feedback(0.5,"Suspended: obstacle on " + target_);
        return;
    }
    if (!msg->blocked && state_ == State::WAITING){
        RCLCPP_INFO(get_logger(), "'%s' clear again: resuming the pick", target_.c_str());
        state_ = State::WORKING;

        work_start_ = now();
        send_feedback(0.5, "Resumed picking");
    }
}

void PickAction::publish_tool_status (bool closed)
{
    ToolStatus msg;
    msg.header.stamp = now();
    msg.closed = closed;
    tool_status_pub_->publish(msg);
}

int main(int argc, char ** argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<PickAction>();

    node->set_parameter(rclcpp::Parameter("action_name", "pick"));
    node->trigger_transition(lifecycle_msgs::msg::Transition::TRANSITION_CONFIGURE);

    rclcpp::spin(node->get_node_base_interface());
    rclcpp::shutdown();

    return 0;
}
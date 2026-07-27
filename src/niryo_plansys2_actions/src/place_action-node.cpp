#include "place_action-node.hpp"
#include <memory>

using namespace std::placeholders;

PlaceAction::PlaceAction() : ActionExecutorClient("place", 250ms)
{
    QoS qos(1);
    qos.transient_local();
    tool_status_pub_ = create_publisher<ToolStatus>(TOOL_STATUS_TOPIC, qos);

    alert_sub_ = create_subscription<SafetyAlert>(
        "/safety_alert", 10, bind(&PlaceAction::on_alert, this, _1));

    declare_parameter("work_duration", 5.0);
    declare_parameter("wait_timeout", 3.0);
    work_duration_ = get_parameter("work_duration").as_double();
    wait_timeout_ = get_parameter("wait_timeout").as_double();

    state_ = State::IDLE;
}


CallbackReturnT PlaceAction::on_activate(const rclcpp_lifecycle::State & state)
{
    tool_status_pub_->on_activate();
    return ActionExecutorClient::on_activate(state);
}


void PlaceAction::do_work()
{
    if (state_ == State::IDLE){
        // the monitor labels a place alert with the area it is watching
        target_ = get_arguments()[1];

        state_ = State::WORKING;
        work_start_ = now();
        RCLCPP_INFO(get_logger(), "Placing at '%s'", target_.c_str());
        send_feedback(0.0, "Place started");
        return;
    }

    if (state_ == State::WORKING){
        //TODO: stub. The real implementation commands the gripper through the
        //tools_commander action and finishes on its result, not on a timer.
        const double elapsed = (now() - work_start_).seconds();

        if (elapsed >= work_duration_){
            // the tool status is a post-condition echo: publish it only when the
            // operation actually completed, never on an aborted one
            publish_tool_status(false);
            state_ = State::IDLE;
            finish(true, 1.0, "Place completed");
            return;
        }

        send_feedback(elapsed / work_duration_, "Placing");
        return;
    }

    if (state_ == State::WAITING){
        if ((now() - wait_start_).seconds() > wait_timeout_){
            RCLCPP_WARN(get_logger(), "Obstacle on '%s' persists: aborting the place",
                target_.c_str());
            state_ = State::IDLE;
            finish(false, 0.0, "Obstacle on " + target_);
        }
        return;
    }
}


void PlaceAction::on_alert(const SafetyAlert::SharedPtr msg)
{
    if (msg->target != target_)
        return;

    if (msg->blocked && state_ == State::WORKING){
        RCLCPP_WARN(get_logger(), "Obstacle on '%s': suspending the place", target_.c_str());
        state_ = State::WAITING;
        wait_start_ = now();

        //TODO: stub. The real implementation cancels the gripper goal here.

        send_feedback(0.5, "Suspended: obstacle on " + target_);
        return;
    }

    if (!msg->blocked && state_ == State::WAITING){
        RCLCPP_INFO(get_logger(), "'%s' clear again: resuming the place", target_.c_str());
        state_ = State::WORKING;
        work_start_ = now();
        send_feedback(0.5, "Resumed");
    }
}


void PlaceAction::publish_tool_status(bool closed)
{
    ToolStatus msg;
    msg.header.stamp = now();
    msg.closed = closed;
    tool_status_pub_->publish(msg);
}


int main(int argc, char ** argv)
{
    init(argc, argv);
    auto node = std::make_shared<PlaceAction>();

    node->set_parameter(rclcpp::Parameter("action_name", "place"));
    node->trigger_transition(lifecycle_msgs::msg::Transition::TRANSITION_CONFIGURE);

    spin(node->get_node_base_interface());
    shutdown();
    return 0;
}
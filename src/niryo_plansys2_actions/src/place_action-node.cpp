#include "plansys2_executor/ActionExecutorClient.hpp"
#include "rclcpp/rclcpp.hpp"

#include "niryo_env_interfaces/msg/tool_status.hpp"

using namespace std::chrono_literals;
using namespace plansys2;

using ToolStatus = niryo_env_interfaces::msg::ToolStatus;
using CallbackReturnT = rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn;

class PlaceAction : public ActionExecutorClient
{
public:
    PlaceAction() : ActionExecutorClient("place", 250ms) 
    {
        rclcpp::QoS qos(1);
        qos.transient_local();

        tool_status_pub_ = create_publisher<ToolStatus>(TOOL_STATUS_TOPIC, qos);
    }
    CallbackReturnT on_activate(const rclcpp_lifecycle::State &state) override
    {
        tool_status_pub_->on_activate();
        return ActionExecutorClient::on_activate(state);
    }
private:
    void do_work()
    {
        RCLCPP_INFO(get_logger(), "Place action executed");

        publish_tool_status(false);
        finish(true, 1.0, "Place completed");
    }

    void publish_tool_status(bool closed)
    {
        ToolStatus msg;
        msg.header.stamp = now();
        msg.closed = closed;
        tool_status_pub_->publish(msg);
    }

    static constexpr const char* TOOL_STATUS_TOPIC = "/arm_1/tool_status";
    rclcpp_lifecycle::LifecyclePublisher<ToolStatus>::SharedPtr tool_status_pub_;
};

int main(int argc, char ** argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<PlaceAction>();


    node->set_parameter(rclcpp::Parameter("action_name", "place"));
    node->trigger_transition(lifecycle_msgs::msg::Transition::TRANSITION_CONFIGURE);

    rclcpp::spin(node->get_node_base_interface());
    rclcpp::shutdown();

    return 0;
}
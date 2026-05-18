#include "plansys2_executor/ActionExecutorClient.hpp"
#include "rclcpp/rclcpp.hpp"

using namespace std::chrono_literals;
using namespace plansys2;

class PickAction : public ActionExecutorClient
{
public:
    PickAction() : ActionExecutorClient("pick", 250ms) {}

private:
    void do_work()
    {
        RCLCPP_INFO(get_logger(), "Pick action executed");
        finish(true, 1.0, "Pick completed");
    }
};

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
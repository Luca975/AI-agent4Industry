#include "plansys2_executor/ActionExecutorClient.hpp"
#include "rclcpp/rclcpp.hpp"

using namespace std::chrono_literals;
using namespace plansys2;

class PlaceAction : public ActionExecutorClient
{
public:
    PlaceAction() : ActionExecutorClient("place", 250ms) {}

private:
    void do_work()
    {
        RCLCPP_INFO(get_logger(), "Place action executed");
        finish(true, 1.0, "Place completed");
    }
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
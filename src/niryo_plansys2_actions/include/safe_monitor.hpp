#pragma once

#include "rclcpp/rclcpp.hpp"
#include "plansys2_msgs/msg/action_execution_info.hpp"
#include "niryo_plansys2_interfaces/msg/safety_alert.hpp"
#include "niryo_plansys2_interfaces/srv/check_path.hpp"
#include "niryo_plansys2_interfaces/srv/check_node.hpp"

#include <string>
#include <vector>

using namespace rclcpp;
using namespace std;

using ActionExecutionInfo = plansys2_msgs::msg::ActionExecutionInfo;
using SafetyAlert = niryo_plansys2_interfaces::msg::SafetyAlert;
using CheckPath = niryo_plansys2_interfaces::srv::CheckPath;
using CheckNode = niryo_plansys2_interfaces::srv::CheckNode;


class SafeMonitor : public Node
{
    public:
        SafeMonitor();

    private:
        void on_action_info(const ActionExecutionInfo::SharedPtr msg);
        void on_timer();
        void publish_verdict(bool blocked);

        Subscription<ActionExecutionInfo>::SharedPtr action_sub_;
        Publisher<SafetyAlert>::SharedPtr alert_pub_;
        Client<CheckPath>::SharedPtr check_path_client_;
        Client<CheckNode>::SharedPtr check_node_client_;
        TimerBase::SharedPtr timer_;

        bool watching_;
        string action_full_name_;
        string action_;
        vector<string> arguments_;
        string target_;

        bool request_in_flight_;   // avoids piling up calls on a slow bridge
        bool last_blocked_;        // hysteresis: publish only on state change
};
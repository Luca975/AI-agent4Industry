#pragma once

#include <string>

#include "rclcpp/rclcpp.hpp"
#include "plansys2_executor/ActionExecutorClient.hpp"
#include "niryo_env_interfaces/msg/tool_status.hpp"
#include "niryo_world_interfaces/msg/safety_alert.hpp"

using namespace rclcpp;
using namespace plansys2;
using namespace std;

using ToolStatus = niryo_env_interfaces::msg::ToolStatus;
using SafetyAlert = niryo_world_interfaces::msg::SafetyAlert;
using CallbackReturnT = rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn;


class PlaceAction : public ActionExecutorClient
{
    public:
        PlaceAction();
        CallbackReturnT on_activate(const rclcpp_lifecycle::State & state) override;

    private:
        // IDLE    -> nothing started yet
        // WORKING -> gripper operation in progress
        // WAITING -> operation suspended after an alert, counting down the micro-wait
        enum class State { IDLE, WORKING, WAITING };

        void do_work();
        void on_alert(const SafetyAlert::SharedPtr msg);
        void publish_tool_status(bool closed);

        Subscription<SafetyAlert>::SharedPtr alert_sub_;
        rclcpp_lifecycle::LifecyclePublisher<ToolStatus>::SharedPtr tool_status_pub_;

        State state_;
        string target_;
        Time work_start_;
        Time wait_start_;
        double work_duration_;
        double wait_timeout_;

        //TODO: hardcoded for the single-arm setup; becomes a parameter with arm_2
        static constexpr const char * TOOL_STATUS_TOPIC = "/arm_1/tool_status";
};
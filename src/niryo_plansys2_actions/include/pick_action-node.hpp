/**
 * @file pick_action-node.hpp
 * @brief PlanSys2 'pick' performer with safety-aware suspend/abort.
 * 
 * A pick has no alternative route - the work area is mandatory -
 * so a persistent obstacle aborts the action, it never triggers a reroute.
 * On success it echoes the new gripper state on the latched tool-status topic.
 * The gripper motion itself is currently a timed stub (see the .cpp TODOs)
 */
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


class PickAction : public ActionExecutorClient 
{
    public:
        PickAction();

        /**
         * @brief Activate the lifecycle tool-status publisher, then delegate to the
         * base-class activation.
         */
        CallbackReturnT on_activate(const rclcpp_lifecycle::State& state) override;

    private:

        /* IDLE -> nothing started yet
           WORKING -> gripper operation in progress
           WAITING -> operation suspended after an alert
        */
        enum class State {IDLE, WORKING, WAITING};


        /**
         * @brief 250ms tick: start the pick when IDLE, count down the (stubbed)
         * work while WORKING, and abort it if the obstacle outlasts the micro-wait
         * while WAITING.
         */
        void do_work();

        /**
         * @brief Suspend the pick when the target node turns blocked, resume
         * when it clears again.
         */
        void on_alert(const SafetyAlert::SharedPtr msg);
        
        /**
         * @brief Publish the gripper state on the latched tool topic.
         * @param closed true after a successfull pick
         */
        void publish_tool_status (bool closed);

        Subscription<SafetyAlert>::SharedPtr alert_sub_;                                ///< /safety_alert
        rclcpp_lifecycle::LifecyclePublisher<ToolStatus>::SharedPtr tool_status_pub_;   ///< Latched gripper-state topic

        State state_;                                                                   ///< Current state (see the State enum)            
        string target_;                                                                 ///< Watched node; matched against SafetyAlert::target
        Time work_start_;                                                               ///< Instant the (stubbed) pick work began
        Time wait_start_;                                                               ///< Instant the micro-wait began

        double work_duration_;                                                          ///< Stubbed pick duration (s); replaced by the real gripper result.
        double wait_timeout_;                                                           ///< Micro-wait duration before aborting (s).

        /*TODO: hardcoded for a single arm, becomes a parameter with the second arm*/
        static constexpr const char* TOOL_STATUS_TOPIC = "/arm_1/tool_status";

};
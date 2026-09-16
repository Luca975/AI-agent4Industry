/**
 * @file place_action-node.hpp
 * @brief PlanSys2 'place' performer with safety-aware suspend/abort.
 * 
 * Mirror of the pick performer: same three-state machine and the same
 * rule that a persistent obstacle aborts rather than reroutes
 */
#pragma once

#include <string>
#include <mutex>
#include <optional>

#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "plansys2_executor/ActionExecutorClient.hpp"
#include "niryo_env_interfaces/msg/tool_status.hpp"
#include "niryo_world_interfaces/msg/safety_alert.hpp"
#include "niryo_ned_ros2_interfaces/action/execute_program.hpp"

using namespace rclcpp;
using namespace plansys2;
using namespace std;

using ToolStatus = niryo_env_interfaces::msg::ToolStatus;
using SafetyAlert = niryo_world_interfaces::msg::SafetyAlert;
using ExecuteProgram = niryo_ned_ros2_interfaces::action::ExecuteProgram;
using GoalHandleExec = rclcpp_action::ClientGoalHandle<ExecuteProgram>;
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

        /** @brief The robot-side release program: equip the tool, open the gripper. */
        string build_code_string() const;

        /** @brief Launch / cancel the release program via the programs_manager action. */
        void send_place_goal();
        void cancel_place_goal();

        void publish_tool_status(bool closed);

        Subscription<SafetyAlert>::SharedPtr alert_sub_;
        rclcpp_action::Client<ExecuteProgram>::SharedPtr exec_client_;       
        rclcpp_lifecycle::LifecyclePublisher<ToolStatus>::SharedPtr tool_status_pub_;    

        GoalHandleExec::SharedPtr goal_handle_;                                         ///< in-flight program (for cancel)
        optional<bool> result_;                                                         ///< result cb: true = success
        mutex result_mtx_;                                                              ///< guards result_
        
        State state_;
        string target_;
        Time wait_start_;
        double wait_timeout_;

        //TODO: hardcoded for the single-arm setup; becomes a parameter with arm_2
        static constexpr const char * TOOL_STATUS_TOPIC = "/arm_1/tool_status";
        static constexpr const char * EXEC_ACTION = "/arm_1/niryo_robot_programs_manager_v2/execute_program";
};
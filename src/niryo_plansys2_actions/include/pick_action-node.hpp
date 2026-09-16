/**
 * @file pick_action-node.hpp
 * @brief PlanSys2 'pick' performer with safety-aware suspend/abort.
 * 
 * A pick has no alternative route - the work area is mandatory -
 * so a persistent obstacle aborts the action, it never triggers a reroute.
 * The pick itself runs robot-side: the performer resolves the target piece's
 * shape/color from /env/scene and ships a wrapper program to the
 * programs_manager 'execute_program' action, finishing on its result.
 * On success it echoes the new gripper state on the latched tool-status topic.
 */
#pragma once

#include <string>
#include <mutex>
#include <optional>
#include <unordered_map>

#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "plansys2_executor/ActionExecutorClient.hpp"
#include "niryo_env_interfaces/msg/tool_status.hpp"
#include "niryo_env_interfaces/msg/env_scene.hpp"
#include "niryo_world_interfaces/msg/safety_alert.hpp"
#include "niryo_ned_ros2_interfaces/action/execute_program.hpp"

using namespace rclcpp;
using namespace plansys2;
using namespace std;

using ToolStatus = niryo_env_interfaces::msg::ToolStatus;
using EnvScene = niryo_env_interfaces::msg::EnvScene;
using SafetyAlert = niryo_world_interfaces::msg::SafetyAlert;
using ExecuteProgram = niryo_ned_ros2_interfaces::action::ExecuteProgram;
using GoalHandleExec = rclcpp_action::ClientGoalHandle<ExecuteProgram>;
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

        /** @brief Cache the last /env/scene for target resolution. */
        void on_scene(const EnvScene::SharedPtr msg);

        /**
         * @brief Resolve the target piece (3rd action argument) into the camera
         * filters, from the last /env/scene. False if the piece isn't in scene.
         */
        bool resolve_target(string& shape_out, string& color_out);
        
        /** @brief Build the robot-side wrapper program with the filters injected. */
        string build_code_string(const string& shape, const string& color) const;

        /** @brief Launch / cancel the pick program via the programs_manager action. */
        void send_pick_goal(const string& shape, const string& color);
        void cancel_pick_goal();

        /**
         * @brief Publish the gripper state on the latched tool topic.
         * @param closed true after a successfull pick
         */
        void publish_tool_status (bool closed);

        Subscription<SafetyAlert>::SharedPtr alert_sub_;                                ///< /safety_alert
        Subscription<EnvScene>::SharedPtr scene_sub_;                                   ///< /env_scene 
        rclcpp_action::Client<ExecuteProgram>::SharedPtr exec_client_;                  ///< execute_program
        rclcpp_lifecycle::LifecyclePublisher<ToolStatus>::SharedPtr tool_status_pub_;   ///< Latched gripper-state topic

        EnvScene::SharedPtr last_scene_;                                               ///< last cached scene
        mutex scene_mtx_;                                                              ///< guards last_scene_

        GoalHandleExec::SharedPtr goal_handle_;                                        ///< in-flight program (for cancel)
        optional<bool> result_;                                                        ///< result cb: true = success
        mutex result_mtx_;                                                             ///< guards result_ 

        State state_;                                                                   ///< Current state (see the State enum)            
        string target_;                                                                 ///< Watched node; matched against SafetyAlert::target
        string obj_shape_, obj_color_;                                                 ///< resolved filters, kept for resume

        Time wait_start_;                                                               ///< Instant the micro-wait began
        double wait_timeout_;                                                           ///< Micro-wait duration before aborting (s).

        static constexpr const char* WORKSPACE_NAME = "workspace_1";
        static constexpr const char* SCENE_TOPIC = "/env/scene";
        /*TODO: hardcoded for a single arm, becomes a parameter with the second arm*/
        static constexpr const char* TOOL_STATUS_TOPIC = "/arm_1/tool_status";
        static constexpr const char* EXEC_ACTION = "/arm_1/niryo_robot_programs_manager_v2/execute_program";

        /// class_id (/env/scene) -> ObjectShape the camera can classify; default "ANY".
        static const unordered_map<string,string> CLASS_TO_SHAPE;

};
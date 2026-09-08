/**
 * @file safe_monitor.hpp
 * @brief Human-safety monitor:: watches the action currently executing and warns
 *        the performer when a human enter its path or target.
 * 
 * It never commands the arm. It subscribes to PlanSys2 action execution info to
 * know what is running, polls the world model at a fixed rate for the occupancy
 * of the relevant arc (move) or node (pick/place) and emits a SafetyAlert on /safety_alert topic.
 */

#pragma once

#include "rclcpp/rclcpp.hpp"
#include "plansys2_msgs/msg/action_execution_info.hpp"
#include "niryo_world_interfaces/msg/safety_alert.hpp"
#include "niryo_world_interfaces/srv/check_path.hpp"
#include "niryo_world_interfaces/srv/check_node.hpp"

#include <string>
#include <vector>

using namespace rclcpp;
using namespace std;

using ActionExecutionInfo = plansys2_msgs::msg::ActionExecutionInfo;
using SafetyAlert = niryo_world_interfaces::msg::SafetyAlert;
using CheckPath = niryo_world_interfaces::srv::CheckPath;
using CheckNode = niryo_world_interfaces::srv::CheckNode;


class SafeMonitor : public Node
{
    public:
        /**
         * @brief Declare the check_rate and wire up the the subscription,
         *        publisher, service clients and poll timer
         */
        SafeMonitor();

    private:
        /**
         * @brief Track which action is executing and derive the target to watch.
         * 
         * For a move the target is the arc "from->to"; for a pick/place it is the node.
         * Any non-EXECUTING status on the watched action stops the watch. Actions that are neither move
         * nor pick/place are not monitored
         */
        void on_action_info(const ActionExecutionInfo::SharedPtr msg);

        /**
         * @brief Poll the world model for the watched target and publish a verdict
         * 
         * No-op when nothing is watched or a previous call is still in flight
         * ( @ref request_in_flight_).
         */
        void on_timer();

        /**
         * @brief Publish a SafetyAlert, but only on a blocked/clear transition.
         * @param blocked true if the watched target is currently occupied
         */
        void publish_verdict(bool blocked);

        Subscription<ActionExecutionInfo>::SharedPtr action_sub_;       ///< /action_execution_info (PlanSys2)
        Publisher<SafetyAlert>::SharedPtr alert_pub_;                   ///< /safety_alert
        Client<CheckPath>::SharedPtr check_path_client_;                ///< /world_model_server/check_path (move targets)
        Client<CheckNode>::SharedPtr check_node_client_;                ///< /world_model_server/check_node (pick/place targets)
        TimerBase::SharedPtr timer_;                                    ///< Drives the periodic poll

        bool watching_;                                                 ///< Whether an action is currently being monitored.
        string action_full_name_;                                       ///< PlanSys2 full name of the watched action
        string action_;                                                 ///< Action verb (move, pick, place)
        vector<string> arguments_;                                      ///< Action arguments
        string target_;                                                 ///< Human-readable target: arc "from->to" or node

        bool request_in_flight_;   // avoids piling up calls on a slow bridge
        bool last_blocked_;        // hysteresis: publish only on state change
};
/**
 * @file move_action-node.hpp
 * @brief PlanSys2 'move' performer with reactive, human-safety aware planning
 * 
 * Executes move by commanding the arm through the RobotMove action,
 * of which it is the sole owner. While moving it listens for SafetyAlert
 * on the watched arc and reacts: stop and wait out a transient obstacle, or, if
 * the obstacle persists, return to "from" and fail the action on purpose so
 * PlanSys2/POPF replans around it.
 */
#pragma once

#include <string>

#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "plansys2_executor/ActionExecutorClient.hpp"
#include "niryo_world_interfaces/srv/get_zone.hpp"
#include "niryo_world_interfaces/msg/safety_alert.hpp"
#include "niryo_ned_ros2_interfaces/action/robot_move.hpp"

using namespace rclcpp;
using namespace rclcpp_action;
using namespace plansys2;
using namespace std;

using GetZone = niryo_world_interfaces::srv::GetZone;
using SafetyAlert = niryo_world_interfaces::msg::SafetyAlert;
using RobotMove = niryo_ned_ros2_interfaces::action::RobotMove;
using GoalHandleRobotMove = rclcpp_action::ClientGoalHandle<RobotMove>;

class moveAction : public ActionExecutorClient{
    public:
        moveAction();
    private:

        /*
            IDLE -> nothing dispatched yet
            MOVING -> travelling toward ?to
            WAITING -> arm stopped after an alert, counting down the micro-wait
            RETURNING -> travelling back to ?from before failing the action
        */
        enum class State {IDLE, MOVING, WAITING, RETURNING};

        /**
         * @brief 250 ms tick. Starts the move when IDLE; while WAITING, checks the micro-wait and,
         * once it expires, switches to RETURNING and heads back to ?from
         */
        void do_work();

        /**
         * @brief Build and send the RobotMove goal from a resolved zone pose.
         * Installs the goal-reponse and result callbacks, both guarded by
         * @ref goal_seq_ so a suspended goal's callbacks are ignored.
         */
        void send_move_command(GetZone::Response::SharedPtr response);

        /**
         * @brief Resolve a zone via GetZone, then send the move command for it.
         * An unknown zone finishes the action as failed.
         * @param zone Target node to travel to
         */
        void dispatch_move(const string& zone);

        /**
         * @brief React to a SafetyAlert on the watched arc: stop while MOVING when
         * it turns blocked, resume when it clears again.
         */
        void on_alert(const SafetyAlert::SharedPtr msg);



        rclcpp::Client<GetZone>::SharedPtr zone_client_;                ///< /world_model_server/get_zone (pose lookup)
        rclcpp_action::Client<RobotMove>::SharedPtr move_client_;       ///< Driver motion action client
        Subscription<SafetyAlert>::SharedPtr alert_sub_;                ///< /safety_alert

        GoalHandleRobotMove::SharedPtr goal_handle_;                    ///< Handle of the in-flight motion goal; null when none

        State state_;                                                   ///< Current state (see the State enum)
        string from_;                                                   ///< Origin node of the move        
        string to_;                                                     ///< Destinantion node of the move
        string target_;                                                 ///< Watched arc "from->to"; matched against SafetyAlert::target
        Time wait_start_;                                               ///< Instant the micro-wait began (WAITING)
        double wait_timeout_;                                           ///< Micro-wait duration before giving up and returning (s)
        uint64_t goal_seq_;                                             ///< Monotonic goal counter; callbacks from a stale goal are dropped

}; 
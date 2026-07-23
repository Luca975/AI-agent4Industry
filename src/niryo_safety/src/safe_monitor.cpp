#include "safe_monitor.hpp"

SafeMonitor::SafeMonitor() : Node("safe_monitor")
{
    declare_parameter("check_rate", 10.0);
    const double rate = get_parameter("check_rate").as_double();

    watching_ = false;
    request_in_flight_ = false;
    last_blocked_ = false;

    action_sub_ = create_subscription<ActionExecutionInfo>(
        "/action_execution_info", 100,
        bind(&SafeMonitor::on_action_info, this, placeholders::_1)
    );

    alert_pub_ = create_publisher<SafetyAlert>("/safety_alert", 10);

    check_path_client_ = create_client<CheckPath>("/world_model_server/check_path");
    check_node_client_ = create_client<CheckNode>("/world_model_server/check_node");

    timer_ = create_wall_timer(
        chrono::duration<double>(1.0 / rate),
        bind(&SafeMonitor::on_timer, this)
    );

    RCLCPP_INFO(get_logger(), "Safe monitor running at %.1f Hz", rate);
}


void SafeMonitor::on_action_info(const ActionExecutionInfo::SharedPtr msg)
{
    if (msg->status == ActionExecutionInfo::EXECUTING){

        if (msg->action_full_name == action_full_name_){
            return;   // same action, nothing to update
        }

        action_full_name_ = msg->action_full_name;
        action_ = msg->action;
        arguments_ = msg->arguments;

        // move(robot, from, to) -> the arc; pick/place(robot, area, piece) -> the node
        if (action_ == "move" && arguments_.size() >= 3){
            target_ = arguments_[1] + "->" + arguments_[2];
            watching_ = true;
        } else if ((action_ == "pick" || action_ == "place") && arguments_.size() >= 2){
            target_ = arguments_[1];
            watching_ = true;
        } else {
            watching_ = false;
            RCLCPP_WARN(get_logger(), "Action '%s' not monitored", action_.c_str());
            return;
        }

        last_blocked_ = false;
        RCLCPP_INFO(get_logger(), "Watching %s on %s", action_.c_str(), target_.c_str());
        return;
    }

    // any other status on the watched action means it is over
    if (watching_ && msg->action_full_name == action_full_name_){
        watching_ = false;
        action_full_name_.clear();
        RCLCPP_INFO(get_logger(), "Stopped watching %s", action_.c_str());
    }
}


void SafeMonitor::on_timer()
{
    if (!watching_ || request_in_flight_){
        return;
    }

    // captured by value: the cached action may change before the response lands,
    // and a verdict about an action that is no longer running must be dropped
    const string pending_action = action_full_name_;

    if (action_ == "move"){
        if (!check_path_client_->service_is_ready()){
            return;
        }

        auto req = std::make_shared<CheckPath::Request>();
        req->from_node = arguments_[1];
        req->to_node = arguments_[2];

        request_in_flight_ = true;
        check_path_client_->async_send_request(req,
            [this, pending_action](Client<CheckPath>::SharedFuture future){
                request_in_flight_ = false;
                auto res = future.get();

                if (!res->success){
                    // unknown node is a configuration bug, not a safety event:
                    // do not stop the arm for it
                    RCLCPP_ERROR(get_logger(), "check_path failed on %s", target_.c_str());
                    return;
                }
                if (pending_action != action_full_name_){
                    return;   // the action changed while the call was in flight
                }
                publish_verdict(!res->clear);
            });

    } else {
        if (!check_node_client_->service_is_ready()){
            return;
        }

        auto req = std::make_shared<CheckNode::Request>();
        req->node = arguments_[1];

        request_in_flight_ = true;
        check_node_client_->async_send_request(req,
            [this, pending_action](Client<CheckNode>::SharedFuture future){
                request_in_flight_ = false;
                auto res = future.get();

                if (!res->success){
                    RCLCPP_ERROR(get_logger(), "check_node failed on %s", target_.c_str());
                    return;
                }
                if (pending_action != action_full_name_){
                    return;
                }
                publish_verdict(!res->clear);
            });
    }
}


void SafeMonitor::publish_verdict(bool blocked)
{
    // hysteresis: the performer gets one message when the invariant falls and one
    // when it is restored, not a stream at the polling rate
    if (blocked == last_blocked_){
        return;
    }
    last_blocked_ = blocked;

    SafetyAlert alert;
    alert.action_full_name = action_full_name_;
    alert.blocked = blocked;
    alert.target = target_;
    alert_pub_->publish(alert);

    if (blocked){
        RCLCPP_WARN(get_logger(), "BLOCKED: %s", target_.c_str());
    } else {
        RCLCPP_INFO(get_logger(), "CLEAR: %s", target_.c_str());
    }
}


int main(int argc, char **argv)
{
    init(argc, argv);
    auto node = std::make_shared<SafeMonitor>();
    spin(node);
    shutdown();
    return 0;
}
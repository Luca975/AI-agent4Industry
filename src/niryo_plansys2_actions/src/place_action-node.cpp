#include "place_action-node.hpp"
#include <memory>
#include <sstream>

using namespace std::placeholders;

PlaceAction::PlaceAction() : ActionExecutorClient("place", 250ms)
{
    QoS qos(1);
    qos.transient_local();
    tool_status_pub_ = create_publisher<ToolStatus>(TOOL_STATUS_TOPIC, qos);

    alert_sub_ = create_subscription<SafetyAlert>(
        "/safety_alert", 10, bind(&PlaceAction::on_alert, this, _1));

    exec_client_ = rclcpp_action::create_client<ExecuteProgram>(this, EXEC_ACTION);

    declare_parameter("wait_timeout", 3.0);
    wait_timeout_ = get_parameter("wait_timeout").as_double();

    state_ = State::IDLE;
}


CallbackReturnT PlaceAction::on_activate(const rclcpp_lifecycle::State & state)
{
    tool_status_pub_->on_activate();
    return ActionExecutorClient::on_activate(state);
}

string PlaceAction::build_code_string() const
{
    // Standalone wrapper program: equip the tool, then release by opening the gripper.
    // update_tool() sets the current tool so open_gripper() acts on it; any wrapper
    // error exits non-zero -> execute_program returns -327 -> emergency path.
    ostringstream py;
    py << "from niryo_robot_python_ros_wrapper import NiryoRosWrapper\n"
       << "from niryo_robot_python_ros_wrapper.CollisionPolicy import CollisionPolicy\n"
       << "robot = NiryoRosWrapper.init_with_node(collision_policy=CollisionPolicy.SOFT)\n"
       << "robot.update_tool()\n"
       << "robot.open_gripper()\n";
    return py.str();
}

void PlaceAction::send_place_goal()
{
    { lock_guard<mutex> lk(result_mtx_); result_.reset(); }
    goal_handle_.reset();

    if (!exec_client_->wait_for_action_server(1s)){
        RCLCPP_ERROR(get_logger(), "execute_program server unavailable");
        lock_guard<mutex> lk(result_mtx_); result_ = false;
        return;
    }

    ExecuteProgram::Goal goal;
    goal.program_id = "";
    goal.code_string = build_code_string();

    rclcpp_action::Client<ExecuteProgram>::SendGoalOptions opts;
    opts.goal_response_callback =
        [this](GoalHandleExec::SharedPtr gh){
            if (!gh){ lock_guard<mutex> lk(result_mtx_); result_ = false; }   // rejected
            else goal_handle_ = gh;
        };
    opts.feedback_callback =
        [this](GoalHandleExec::SharedPtr, shared_ptr<const ExecuteProgram::Feedback> fb){
            RCLCPP_INFO(get_logger(), "place program: %s", fb->output.c_str());
        };
    opts.result_callback =
        [this](const GoalHandleExec::WrappedResult & res){
            const bool ok = (res.code == rclcpp_action::ResultCode::SUCCEEDED)
                         && (res.result->status == 1);   // CommandStatus::SUCCESS
            lock_guard<mutex> lk(result_mtx_); result_ = ok;
        };

    exec_client_->async_send_goal(goal, opts);
}

void PlaceAction::cancel_place_goal()
{
    if (goal_handle_){
        exec_client_->async_cancel_goal(goal_handle_);   // -> stop_execution robot-side
        goal_handle_.reset();
    }
}

void PlaceAction::do_work()
{
    if (state_ == State::IDLE){
        // the monitor labels a place alert with the area it is watching
        target_ = get_arguments()[1];

        send_place_goal();
        state_ = State::WORKING;
        RCLCPP_INFO(get_logger(), "Placing (release) at '%s'", target_.c_str());
        send_feedback(0.0, "Place started");
        return;
    }

    if (state_ == State::WORKING){
        optional<bool> res;
        { lock_guard<mutex> lk(result_mtx_); res = result_; }

        if (!res.has_value()){
            send_feedback(0.5, "Placing");
            return;
        }
        if (*res){
            // post-condition echo: gripper is now open. Publish only on completion.
            publish_tool_status(false);
            state_ = State::IDLE;
            finish(true, 1.0, "Place completed");
        } else {
            state_ = State::IDLE;
            finish(false, 0.0, "Place program failed");
        }
        return;
    }

    if (state_ == State::WAITING){
        if ((now() - wait_start_).seconds() > wait_timeout_){
            RCLCPP_WARN(get_logger(), "Obstacle on '%s' persists: aborting the place",
                target_.c_str());
            state_ = State::IDLE;
            finish(false, 0.0, "Obstacle on " + target_);
        }
        return;
    }
}


void PlaceAction::on_alert(const SafetyAlert::SharedPtr msg)
{
    if (msg->target != target_)
        return;

    if (msg->blocked && state_ == State::WORKING){
        RCLCPP_WARN(get_logger(), "Obstacle on '%s': suspending the place", target_.c_str());
        cancel_place_goal();
        state_ = State::WAITING;
        wait_start_ = now();
        send_feedback(0.5, "Suspended: obstacle on " + target_);
        return;
    }

    if (!msg->blocked && state_ == State::WAITING){
        RCLCPP_INFO(get_logger(), "'%s' clear again: resuming the place", target_.c_str());
        send_place_goal();
        state_ = State::WORKING;
        send_feedback(0.5, "Resumed");
    }
}


void PlaceAction::publish_tool_status(bool closed)
{
    ToolStatus msg;
    msg.header.stamp = now();
    msg.closed = closed;
    tool_status_pub_->publish(msg);
}


int main(int argc, char ** argv)
{
    init(argc, argv);
    auto node = std::make_shared<PlaceAction>();

    node->set_parameter(rclcpp::Parameter("action_name", "place"));
    node->trigger_transition(lifecycle_msgs::msg::Transition::TRANSITION_CONFIGURE);

    spin(node->get_node_base_interface());
    shutdown();
    return 0;
}
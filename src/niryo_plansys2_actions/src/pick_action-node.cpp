#include "pick_action-node.hpp"
#include <memory>
#include <sstream>
#include <algorithm>

using namespace std::placeholders;


const unordered_map<string,string> PickAction::CLASS_TO_SHAPE = {
    {"circle", "CIRCLE"},
    {"cube", "SQUARE"}
};



PickAction::PickAction() : ActionExecutorClient("pick",250ms)
{
    // Lacthed (transient_local): the world model must see the last gripper state
    // even if it subscribes after this pick published. Both ends use it
    QoS qos(1);
    qos.transient_local();
    tool_status_pub_ = create_publisher<ToolStatus>(TOOL_STATUS_TOPIC, qos);

    alert_sub_ = create_subscription<SafetyAlert>("/safety_alert",10, 
                            bind(&PickAction::on_alert, this, _1));

    scene_sub_ = create_subscription<EnvScene>(SCENE_TOPIC, 10,
                    bind(&PickAction::on_scene, this, _1));                        

    exec_client_ = rclcpp_action::create_client<ExecuteProgram>(this, EXEC_ACTION);

    declare_parameter("wait_timeout",3.0);
    wait_timeout_ = get_parameter("wait_timeout").as_double();

    state_ = State::IDLE;
}

CallbackReturnT PickAction::on_activate(const rclcpp_lifecycle::State& state)
{
    tool_status_pub_->on_activate();
    return ActionExecutorClient::on_activate(state);
}

void PickAction::on_scene(const EnvScene::SharedPtr msg)
{
    lock_guard<mutex> lk(scene_mtx_);
    last_scene_ = msg;
}

bool PickAction::resolve_target(string& shape_out, string& color_out)
{
    const string obj_id = get_arguments()[2];   // (pick ?arm ?area ?piece)

    EnvScene::SharedPtr scene;
    {
        lock_guard<mutex> lk(scene_mtx_);
        scene = last_scene_;
    }
    if (!scene){
        RCLCPP_ERROR(get_logger(), "No /env/scene received yet");
        return false;
    }

    for (const auto& obj : scene->objects){
        if (obj.id != obj_id) continue;

        // /env/scene colors are lowercase; the wrapper wants "RED"/"GREEN"/"BLUE".
        color_out = obj.color;
        transform(color_out.begin(), color_out.end(), color_out.begin(), ::toupper);
        if (color_out.empty()){
            RCLCPP_ERROR(get_logger(), "Object '%s' has no color in scene", obj_id.c_str());
            return false;
        }

        // Unmapped class_id -> "ANY": let color alone discriminate.
        string cls = obj.class_id;
        transform(cls.begin(), cls.end(), cls.begin(), ::tolower);
        auto it = CLASS_TO_SHAPE.find(cls);
        shape_out = (it != CLASS_TO_SHAPE.end()) ? it->second : "ANY";
        return true;
    }
    RCLCPP_ERROR(get_logger(), "Object '%s' not in /env/scene", obj_id.c_str());
    return false;
}

string PickAction::build_code_string(const string& shape, const string& color) const
{
    // Standalone wrapper program: detect the piece in the workspace, then pick.
    // Not found -> exit(1) so execute_program returns -327 -> emergency path.
    // as_list=True + Pose(*pose): get_target_pose_from_cam returns a RobotState,
    // which pick() can't consume (__get_high_pose needs a Pose with .copy()/.z).
    ostringstream py;
    py << "from niryo_robot_python_ros_wrapper import NiryoRosWrapper, Pose\n"
       << "from niryo_robot_python_ros_wrapper.CollisionPolicy import CollisionPolicy\n"
       << "import sys\n"
       << "robot = NiryoRosWrapper.init_with_node(collision_policy=CollisionPolicy.SOFT)\n"
       << "robot.calibrate_auto()\n"
       << "robot.update_tool()\n"
       << "found, pose, _, _ = robot.get_target_pose_from_cam(\n"
       << "    \"" << WORKSPACE_NAME << "\", 0.0, \"" << shape << "\", \"" << color << "\", as_list=True)\n"
       << "if not found:\n"
       << "    sys.exit(1)\n"
       << "robot.pick(Pose(*pose))\n";
    return py.str();
}

void PickAction::send_pick_goal(const string& shape, const string& color)
{
    { lock_guard<mutex> lk(result_mtx_); result_.reset(); }
    goal_handle_.reset();

    // One-shot guard at pick start; the server is long up by dispatch time.
    if (!exec_client_->wait_for_action_server(1s)){
        RCLCPP_ERROR(get_logger(), "execute_program server unavailable");
        lock_guard<mutex> lk(result_mtx_); result_ = false;
        return;
    }

    ExecuteProgram::Goal goal;
    goal.program_id = "";
    goal.code_string = build_code_string(shape, color);

    rclcpp_action::Client<ExecuteProgram>::SendGoalOptions opts;
    opts.goal_response_callback =
        [this](GoalHandleExec::SharedPtr gh){
            if (!gh){ lock_guard<mutex> lk(result_mtx_); result_ = false; }   // rejected
            else goal_handle_ = gh;
        };
    opts.feedback_callback =
        [this](GoalHandleExec::SharedPtr, shared_ptr<const ExecuteProgram::Feedback> fb){
            RCLCPP_INFO(get_logger(), "pick program: %s", fb->output.c_str());
        };
    opts.result_callback =
        [this](const GoalHandleExec::WrappedResult& res){
            const bool ok = (res.code == rclcpp_action::ResultCode::SUCCEEDED)
                         && (res.result->status == 1);   // CommandStatus::SUCCESS
            lock_guard<mutex> lk(result_mtx_); result_ = ok;
        };

    exec_client_->async_send_goal(goal, opts);
}

void PickAction::cancel_pick_goal()
{
    if (goal_handle_){
        exec_client_->async_cancel_goal(goal_handle_);   // -> stop_execution robot-side
        goal_handle_.reset();
    }
}

void PickAction::do_work()
{
    if (state_ == State::IDLE){
        target_ = get_arguments()[1];

        if (!resolve_target(obj_shape_, obj_color_)){
            finish(false, 0.0, "Target piece not resolvable from /env/scene");
            return;
        }        

        send_pick_goal(obj_shape_, obj_color_);

        state_ = State::WORKING;
        RCLCPP_INFO(get_logger(), "Picking '%s' (%s/%s) at '%s'",
                    get_arguments()[2].c_str(), obj_shape_.c_str(), obj_color_.c_str(), target_.c_str());
        send_feedback(0.0, "Pick started");
        return;
    }

    if (state_ == State::WORKING){
        optional<bool> res;
        { lock_guard<mutex> lk(result_mtx_); res = result_; }

        if (!res.has_value()){
            send_feedback(0.5, "Picking");
            return;
        }
        if (*res){
            publish_tool_status(true);
            state_ = State::IDLE;
            finish(true, 1.0, "Pick completed");
        } else {
            state_ = State::IDLE;
            finish(false, 0.0, "Pick program failed");
        }
        return;
    }

    if (state_ == State::WAITING){

        // No fallback for a pick (the work area is mandatory): a persistent
        // obstacle aborts the action and escalates to emergency, it never reroutes.
        if ((now()-wait_start_).seconds() > wait_timeout_){
            RCLCPP_WARN(get_logger(), "Obstacle on '%s' persists: aborting the pick", target_.c_str());
            state_ = State::IDLE;
            finish(false, 0.0, "Obstacle on " + target_);
        }
        return;
    }
}

void PickAction::on_alert(const SafetyAlert::SharedPtr msg)
{
    if (msg->target != target_)
        return;
    
    if (msg->blocked && state_==State::WORKING){
        RCLCPP_WARN(get_logger(), "Obstacle on '%s': suspending the pick", target_.c_str());
        cancel_pick_goal();          // stop the running program
        state_ = State::WAITING;
        wait_start_ = now();
        send_feedback(0.5, "Suspended: obstacle on " + target_);
        return;
    }
    if (!msg->blocked && state_ == State::WAITING){
        RCLCPP_INFO(get_logger(), "'%s' clear again: resuming the pick", target_.c_str());
        send_pick_goal(obj_shape_, obj_color_);   // re-launch from scratch
        state_ = State::WORKING;
        send_feedback(0.5, "Resumed picking");
    }
}

void PickAction::publish_tool_status (bool closed)
{
    ToolStatus msg;
    msg.header.stamp = now();
    msg.closed = closed;
    tool_status_pub_->publish(msg);
}

int main(int argc, char ** argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<PickAction>();

    node->set_parameter(rclcpp::Parameter("action_name", "pick"));
    node->trigger_transition(lifecycle_msgs::msg::Transition::TRANSITION_CONFIGURE);

    rclcpp::spin(node->get_node_base_interface());
    rclcpp::shutdown();

    return 0;
}
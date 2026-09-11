#include <chrono>
#include <stdexcept>
#include <cmath>
#include "world_model_server.hpp"



WorldModelServer::WorldModelServer() : Node("world_model_server")
{
    declare_parameter("zone_thresholds", 0.15);
    declare_parameter("grasp_threshold", 0.05);
    declare_parameter("staleness_threshold", 1.0);
    declare_parameter("arm_name","arm_1");
    declare_parameter("class_to_type", vector<string>{});
    declare_parameter("waypoint_prefix", "wp");
    declare_parameter("human_radius", 0.08);
    declare_parameter("path_clearance", 0.08);

    zone_thresholds = get_parameter("zone_thresholds").as_double();
    grasp_threshold_ = get_parameter("grasp_threshold").as_double();
    staleness_threshold_ = get_parameter("staleness_threshold").as_double();
    arm_name_ = get_parameter("arm_name").as_string();
    waypoint_prefix_ = get_parameter("waypoint_prefix").as_string();
    human_radius_ = get_parameter("human_radius").as_double();
    path_clearance_ = get_parameter("path_clearance").as_double();

    // Param format: one "class_id::type" string per entry; split on the first ':'.
    // Perception speaks class_ids, the rest of the node speaks semantic types.
    const vector<string> class_entries = get_parameter("class_to_type").as_string_array();
    for (const auto& entry : class_entries){
        auto sep = entry.find(':');
        if (sep == string::npos){
            RCLCPP_ERROR(get_logger(), "Malformed class_to_type entry: '%s'", entry.c_str());
            continue;
        }
        class_to_type_[entry.substr(0,sep)] = entry.substr(sep + 1);
    }

    // Areas and waypoints are library poses saved on the robot, fetched from the
    // driver at startup; home is injected from the home_pose param. build_arcs()
    // then wires the hand-built topology over the loaded nodes, so it must run last.
    load_zones_from_robot();
    build_arcs();
    
    // 0 = "never received": check_freshness() treats a zero stamp as "no data yet".
    last_scene_ = Time(0,0, get_clock()->get_clock_type());
    last_arm_ = Time(0,0, get_clock()->get_clock_type());

    gripper_closed_ = false;
    tool_received_ = false;

    // /env/scene: default QoS (reliable, volatile, keep_last/10)
    scene_sub_ = create_subscription<EnvScene>(
        "/env/scene",10,
        bind(&WorldModelServer::on_scene, this, placeholders::_1)
    );

    // Event-driven topic (changes on pick/place): latched via transient_local
    // so a node starting after the last pick still gets the current gripper state.
    QoS tool_qos(1);
    tool_qos.transient_local();
    tool_sub_ = create_subscription<ToolStatus>(
        "/arm_1/tool_status", tool_qos,
        bind(&WorldModelServer::on_tool_status, this, placeholders::_1)
    );
    
    // SensorDataQoS (best_effort, volatile, keep_last/5).
    //TODO: confirm best_effort is the inteded reliability for robot_state.
    arm_sub_ = create_subscription<RobotState>(
        "/arm_1/niryo_robot/robot_state", SensorDataQoS(),
        bind(&WorldModelServer::on_robot_state, this, placeholders::_1)
    );

    service_ = create_service<GetZone>(
        "/world_model_server/get_zone",
        bind(&WorldModelServer::handle_request, this, placeholders::_1, placeholders::_2)
    );

    observe_service_ = create_service<ObserveScene>(
        "/world_model_server/observe_scene",
        bind(&WorldModelServer::handle_observe_req, this, placeholders::_1, placeholders::_2)
    );

    check_path_service_ = create_service<CheckPath>("/world_model_server/check_path",
        bind(&WorldModelServer::handle_check_path, this, placeholders::_1, placeholders::_2)
    );

    check_node_service_ = create_service<CheckNode>("/world_model_server/check_node",
        bind(&WorldModelServer::handle_check_node, this, placeholders::_1, placeholders::_2)
    );
}


void WorldModelServer::load_zones_from_robot()
{
    auto loader = std::make_shared<Node>("world_model_loader");

    const string pose_list_service = "/arm_1/niryo_robot_poses_handlers/get_pose_list";
    const string pose_service = "/arm_1/niryo_robot_poses_handlers/get_pose";
    
    auto pose_list_client = loader->create_client<GetPoseList>(pose_list_service);
    auto pose_client = loader->create_client<GetPose>(pose_service);

    const auto timeout = chrono::seconds(30);
    if (!pose_list_client->wait_for_service(timeout) || !pose_client->wait_for_service(timeout)){
        RCLCPP_FATAL(get_logger(),
            "poses_handlers services unavailable: is the driver up? Aborting.");
        throw runtime_error("world_model_server: poses_handlers services unavailable");
    }

    // 1) Names of every saved pose.
    auto list_req = std::make_shared<GetPoseList::Request>();
    auto list_fut = pose_list_client->async_send_request(list_req);
    if (spin_until_future_complete(loader, list_fut, timeout) != FutureReturnCode::SUCCESS){
        RCLCPP_FATAL(get_logger(), "get_pose_list call failed. Aborting.");
        throw runtime_error("world_model_server: get_pose_list failed");
    }

    auto list_resp = list_fut.get();
    if (list_resp->status != 1){
        RCLCPP_FATAL(get_logger(), "get_pose_list returned status %d: %s",
            list_resp->status, list_resp->message.c_str());
        throw runtime_error("world_model_server: get_pose_list bad status");
    }

    // 2) Full pose of each name; classify AREA vs WAYPOINT by name prefix.
    for (const auto& name : list_resp->name_list){
        auto pose_req = std::make_shared<GetPose::Request>();
        pose_req->name = name;
        auto pose_fut = pose_client->async_send_request(pose_req);
 
        if (spin_until_future_complete(loader, pose_fut, timeout) != FutureReturnCode::SUCCESS){
            RCLCPP_WARN(get_logger(), "get_pose('%s') call failed: skipped", name.c_str());
            continue;
        }
 
        auto pose_resp = pose_fut.get();
        if (pose_resp->status != 1){
            RCLCPP_WARN(get_logger(), "get_pose('%s') status %d: skipped",
                name.c_str(), pose_resp->status);
            continue;
        }
 
        const auto& p = pose_resp->pose;
 
        GetZone::Response record;
        record.position.x = p.position.x;
        record.position.y = p.position.y;
        record.position.z = p.position.z;
        record.rpy.roll = p.rpy.roll;
        record.rpy.pitch = p.rpy.pitch;
        record.rpy.yaw = p.rpy.yaw;
 
        const bool is_wp = (name == HOME_NODE) || (name.rfind(waypoint_prefix_, 0) == 0);
        record.type = is_wp ? SceneObject::WAYPOINT : SceneObject::AREA;
 
        zones_[name] = record;
        RCLCPP_INFO(get_logger(), "Loaded zone '%s' (%s) at (%.3f, %.3f, %.3f)",
            name.c_str(), record.type.c_str(),
            record.position.x, record.position.y, record.position.z);
    }
 
}

void WorldModelServer::build_arcs()
{
    arcs_ = {
        {"conveyor", "wp1"}, {"wp1", "workspace"},
        {"conveyor", "wp2"}, {"wp2", "workspace"},
        {HOME_NODE,  "wp1"}, {HOME_NODE,  "wp2"}
    };
 
    for (const auto& [from, to] : arcs_){
        if (zones_.find(from) == zones_.end())
            RCLCPP_ERROR(get_logger(), "Arc endpoint '%s' is not a known zone", from.c_str());
        if (zones_.find(to) == zones_.end())
            RCLCPP_ERROR(get_logger(), "Arc endpoint '%s' is not a known zone", to.c_str());
    }
 
    RCLCPP_INFO(get_logger(), "Graph built with %zu undirected arcs", arcs_.size());
}


void WorldModelServer::on_scene(const EnvScene::SharedPtr msg)
{
    //Rebuild into a temporary and swap at the end, so objects_ is never seen
    // half-updated by a concurrent service call
    map<string, SceneItem> fresh;

    for (const auto& obj : msg->objects){
        auto it = class_to_type_.find(obj.class_id);
        
        if (it == class_to_type_.end()){
            RCLCPP_WARN(get_logger(),
                "Unknown class '%s' (object '%s'): not in class_to_type, dropped",
            obj.class_id.c_str(),obj.id.c_str());
            continue;
        }

        SceneItem item;
        item.type = it->second;
        item.color = obj.color;
        item.center = obj.pose.position;

        // support = base of the object (center lowered by half its height). A
        // piece belongs to the zone its base rests on, not the one its centroid
        // float over, so zone resolution uses this point rather than the center.
        item.support = obj.pose.position;
        item.support.z = obj.pose.position.z - obj.size.z / 2.0;
        fresh[obj.id] = item;
    }

    objects_ = fresh;
    last_scene_ = now();
}

void WorldModelServer::on_tool_status(const ToolStatus::SharedPtr msg)
{
    gripper_closed_ = msg->closed;
    tool_received_=true;
}
void WorldModelServer::on_robot_state(const RobotState::SharedPtr msg)
{
    arm_position_ = msg->position;
    last_arm_ = now();
}

string WorldModelServer::resolve_zone(const geometry_msgs::msg::Point& p, const string& locatable_type) const
{   
    //Matching rules differ by what is being placed:
    // - PIECE: only AREAs are candidates (a piece lives in a work area and never on a transit waypoint)
    // - HUMAN: matched in XY only with the wider human_radius_. A person is tall and only meaningfully localized
    //          on the ground plane.
    // - anything else (e.g. the arm): full 3D within zone_thresholds.
    const bool areas_only = (locatable_type == SceneObject::PIECE);
    const bool is_human = (locatable_type == SceneObject::HUMAN);
    const double threshold = is_human ? human_radius_ : zone_thresholds;

    double best_dist = numeric_limits<double>::max();
    string best_zone = "";

    for(const auto& [zone_name, zone] : zones_){

        if(areas_only && zone.type != SceneObject::AREA)
            continue;
        
        double dx = p.x - zone.position.x;
        double dy = p.y - zone.position.y;
        double dz = is_human ? 0.0: (p.z - zone.position.z);
        double dist = sqrt(dx*dx + dy*dy + dz*dz);

        if(dist < best_dist){
            best_dist = dist;
            best_zone = zone_name;
        }
    }
    
    // Nearest zone only counts if it si actually within threshold; otherwise the
    // locatable is between zones and resolves to ""
    return (best_dist <= threshold) ? best_zone : "";
}

string WorldModelServer::resolve_held() const
{
    if (!gripper_closed_)
    {
        return "";
    }
    
    // Gripper closed: the held piece is the closest one to the tip within grasp
    // range. seeded with grasp_threshold_ so anything farther can never win.
    double best = grasp_threshold_;
    string held = "";

    for (const auto& [name, item] : objects_) {
        if (item.type != SceneObject::PIECE){
            continue; //a human/obstacle is never held
        }

        double dx = item.center.x - arm_position_.x;
        double dy = item.center.y - arm_position_.y;
        double dz = item.center.z - arm_position_.z;
        double dist = sqrt(dx*dx + dy*dy + dz*dz);

        if(dist < best){
            best = dist;
            held = name;
        }
    }

    // Closed gripper but nothing in range: likely a missed/partial grasp
    // - worth a warning but not an error (the caller decides what to do with "").
    if (held.empty()){
        RCLCPP_WARN(get_logger(), "Gripper is closed but no piece is within %.3f m of it",
        grasp_threshold_);
    }

    return held;
}

string WorldModelServer::check_freshness() const
{
    auto t = now();

    if (last_scene_.nanoseconds() == 0){
        return "no scene received yet on /env/scene";
    }

    double scene_age = (t - last_scene_).seconds();
    if (scene_age > staleness_threshold_){
        return "scene on /env/scene is " + to_string(scene_age) + " s old";
    }

    if (last_arm_.nanoseconds() == 0){
        return "no arm state received yet on /arm_1/niryo_robot/robot_state";
    }

    double arm_age = (t - last_arm_).seconds();
    if (arm_age > staleness_threshold_){
        return "arm state is " + to_string(arm_age) + " s old";
    }

    /*tool state is deliberately not checked: it is related to an event, not to a data stream,
    so the last pick may be old and perfectly valid*/

    return "";
}


bool WorldModelServer::is_node_clear(const string& node) const
{
    auto it = zones_.find(node);
    if (it == zones_.end())
        return false;
    
    // A node is blocked if any human stands within humand_radius_ of it (XY)
    for (const auto& [name, item] : objects_){
        if (item.type != SceneObject::HUMAN)
            continue;
        
        double dx = item.center.x - it->second.position.x;
        double dy = item.center.y - it->second.position.y;

        if (sqrt(dx*dx + dy*dy) <= human_radius_){
            RCLCPP_DEBUG(get_logger(), "Human '%s' occupies node %s",
            name.c_str(), node.c_str());
            return false;
        }
    }

    return true;
}

bool WorldModelServer::is_path_clear(const string& from, const string& to)const
{
    auto it_a = zones_.find(from);
    auto it_b = zones_.find(to);

    if (it_a == zones_.end() || it_b == zones_.end())
        return false;
    
    const auto& a = it_a->second.position;
    const auto& b = it_b->second.position;

    double vx = b.x - a.x;
    double vy = b.y - a.y;
    double vv = vx*vx + vy*vy;

    for (const auto& [name, item] : objects_){
        
        if (item.type != SceneObject::HUMAN)
            continue;

        // Project the human onto segment AB and clamp t to [0,1] so the closest
        // point is the true nearest point on the segment (endpoints included,
        // not the infinite line). Degenerate segment (vv~0) falls back to t=0,
        // i.e. distance to A.        
        double t = 0.0;
        if (vv > 1e-9){
            t = ((item.center.x - a.x)*vx + (item.center.y - a.y)*vy) / vv;
            t = clamp(t, 0.0, 1.0);
        }

        double px = a.x + t*vx;
        double py = a.y + t*vy;
        double dx = item.center.x - px;
        double dy = item.center.y - py;        

        // Blocked if the human is closer to the segment than the clearance. XY only.
        if (sqrt(dx*dx + dy*dy) < path_clearance_){
            RCLCPP_DEBUG(get_logger(), "Human '%s' obstructs the path %s -> %s",
                name.c_str(), from.c_str(), to.c_str());
            return false;
        }
    }

    return true;
}

void WorldModelServer::handle_request(const shared_ptr<GetZone::Request> request, shared_ptr<GetZone::Response> response)
{
    auto it = zones_.find(request->zone);
    if(it != zones_.end()){
        *response = it->second;
        response->success = true;
    } else {
        RCLCPP_WARN(get_logger(), "Zone not found: %s", request->zone.c_str());
        response->success = false;
    }
}

void WorldModelServer::handle_observe_req(const shared_ptr<ObserveScene::Request> request, shared_ptr<ObserveScene::Response> response)
{
    (void)request;

    // Gate first: a partial/stale snapshot would yield a plausible-but-wrong PDDL
    // problem that the planner silently accepts, so refuse all-or-nothing
    string stale = check_freshness();

    if (!stale.empty()){
        RCLCPP_WARN(get_logger(), "observe_scene refused: %s",stale.c_str());
        response->success = false;
        response->error_info = stale;
        return;
    }

    if (!tool_received_){
        RCLCPP_INFO_ONCE(get_logger(), "No tool_status yet: assuming the gripper is open");
    }

    const string held_id = resolve_held();
    
    for (const auto& [name, item] : objects_){
        SceneObject obj;
        obj.name = name;
        obj.type = item.type;
        obj.color = item.color;
        obj.held = (name == held_id);

        // A held object has no location: it is on the tool.
        obj.location = obj.held ? "" : resolve_zone(item.support, item.type);
        if (obj.location.empty() && !obj.held){
            RCLCPP_WARN(get_logger(), "Locatable '%s' is outside every zone", name.c_str());
        }

        response->objects.push_back(obj);
    }

    // The arm is always emitted as a fact. If it is between zones, report the
    // SOME_PLACE fallback rather than "" so it always has a valid location.
    SceneObject arm;
    arm.name = arm_name_;
    arm.type = SceneObject::ROBOT;
    arm.held = false;
    arm.color = "";
    const string arm_zone = resolve_zone(arm_position_, SceneObject::ROBOT);
    arm.location = arm_zone.empty() ? SOME_PLACE : arm_zone;

    RCLCPP_DEBUG(get_logger(),"Arm '%s' location: '%s'",arm_name_.c_str(), arm.location.c_str());

    response -> objects.push_back(arm);

    // Emit every static node as a fact too, so the problem generator sees the
    // full topology, not only the nodes that currently have an object on them.
    for (const auto& [zone_name, zone] : zones_){
        (void)zone;
        SceneObject obj;
        obj.name = zone_name;
        obj.type = zone.type;
        obj.location = "";
        obj.held = false;
        obj.color = "";

        response->objects.push_back(obj);
    }

    for (const auto& [from, to] : arcs_){
        const bool clear = is_path_clear(from, to);

        // The graph is undirected: emit both directions, so the problem generator
        // transcribes instead of having to reason about symmetry.
        ScenePath p;
        p.from_node = from;
        p.to_node = to;
        p.clear = clear;
        response->paths.push_back(p);

        ScenePath q;
        q.from_node = to;
        q.to_node = from;
        q.clear = clear;
        response->paths.push_back(q);
    }

    response->success = true;
    response->error_info = "";
}

void WorldModelServer::handle_check_path(const shared_ptr<CheckPath::Request> request, shared_ptr<CheckPath::Response> response)
{
    if (zones_.count(request->from_node) == 0 || zones_.count(request->to_node) == 0){
        RCLCPP_WARN(get_logger(), "check_path: unknown node '%s' or '%s'",
            request->from_node.c_str(), request->to_node.c_str());
        response->success = false;
        response->clear = false;
        return;
    }

    response->clear = is_path_clear(request->from_node, request->to_node);
    response->success = true;
    }

void WorldModelServer::handle_check_node(const shared_ptr<CheckNode::Request> request, shared_ptr<CheckNode::Response> response)
{
    if (zones_.count(request->node) == 0){
        RCLCPP_WARN(get_logger(), "check_node: unknown node '%s'", request->node.c_str());
        response->success = false;
        response->clear = false;
        return;
    }

    response->clear = is_node_clear(request->node);
    response->success = true;   
}

int main(int argc, char **argv)
{
    init(argc, argv);
    auto node = make_shared<WorldModelServer>();
    spin(node);
    shutdown();
    return 0;
}
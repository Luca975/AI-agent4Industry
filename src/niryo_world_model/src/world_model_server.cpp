#include <fstream>
#include <sstream>
#include <cmath>
#include "world_model_server.hpp"



WorldModelServer::WorldModelServer() : Node("world_model_server")
{
    declare_parameter("zones_file", "");
    declare_parameter("zone_thresholds", 0.15);
    declare_parameter("grasp_threshold", 0.05);
    declare_parameter("staleness_threshold", 1.0);
    declare_parameter("arm_name","arm_1");
    declare_parameter("class_to_type", vector<string>{});
    declare_parameter("waypoint_offsets", vector<double>{0.02, 0.22});
    declare_parameter("waypoint_height",0.35);
    declare_parameter("human_radius", 0.08);
    declare_parameter("path_clearance", 0.08);

    string csv_path = get_parameter("zones_file").as_string();
    zone_thresholds = get_parameter("zone_thresholds").as_double();
    grasp_threshold_ = get_parameter("grasp_threshold").as_double();
    staleness_threshold_ = get_parameter("staleness_threshold").as_double();
    arm_name_ = get_parameter("arm_name").as_string();
    waypoint_offsets_ = get_parameter("waypoint_offsets").as_double_array();
    waypoint_height_ = get_parameter("waypoint_height").as_double();
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

    //Order matters: generate_waypoints() must run before build_arcs(), which
    // wires the freshly created waypoints to home.
    read_zones(csv_path);
    generate_waypoints();
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


void WorldModelServer::read_zones(const string& filename)
{
    ifstream file(filename);

    if(!file.is_open()){
        RCLCPP_ERROR(get_logger(), "Could not open file: %s", filename.c_str());
        return;
    }

    string line;
    while(getline(file,line)){
        istringstream ss(line);
        string name, type;
        double x,y,z,r,p,yaw;
        char sep;

        // name and type are comma-delimited; the six pose fields are then read
        // numerically, with the commas between them absorbed into 'sep' and dropped.
        getline(ss,name,',');
        getline(ss,type,',');
        ss >> x >> sep >> y >> sep >> z >> sep >> r >> sep >> p >> sep >> yaw;

        //Only the areas live in the config: they are a static map
        if(type != SceneObject::AREA && type != SceneObject::WAYPOINT){
            RCLCPP_WARN(get_logger(),
                "Ignoring non-location row '%s': objects come from /env/scene",
                name.c_str());
            continue;
        }
        

        // stations_ keeps AREA names in file order: generate_waypoints() pairs,
        // them consecutively, so the CSV row order defines which stations get
        // a waypoint pair between them.
        if (type == SceneObject::AREA){
            stations_.push_back(name);
        }
        
        GetZone::Response response;
        response.position.x = x;
        response.position.y = y;
        response.position.z = z;
        response.rpy.roll = r;
        response.rpy.pitch = p;
        response.rpy.yaw = yaw;
        response.type = type;

        zones_[name] = response;
        
    }
}

void WorldModelServer::build_arcs()
{
    for (const auto& [name, zone] : zones_){
        if (zone.type == SceneObject::WAYPOINT && name != HOME_NODE)
            arcs_.emplace_back(HOME_NODE, name);
    }

    RCLCPP_INFO(get_logger(),
        "Graph build with %zu undirect arcs", arcs_.size());
}


void WorldModelServer::generate_waypoints()
{
    if (stations_.size() < 2){
        RCLCPP_WARN(get_logger(), "Fewer than two stations: no waypoint generated");
        return;
    }

    size_t wp_index = 1;
    for (size_t i = 0; i+1 < stations_.size(); i++){

        vector<string> pair_wps;
        const auto& a = zones_.at(stations_[i]).position;
        const auto& b = zones_.at(stations_[i+1]).position;

        // ref = midpoint of the two stations; the waypoints sit on the line
        // perpendiculare to AB through this midpoint.
        double ref_x = 0.5 * (a.x + b.x);
        double ref_y = 0.5 * (a.y + b.y);

        // (nx, ny) = AB rotated 90 degrees, i.e. the direction perpendicular to
        // the segment. Normalized below.
        double nx = -(b.y - a.y);
        double ny = (b.x - a.x);
        double norm = sqrt(nx*nx + ny*ny);

        if (norm < 1e-6){
            RCLCPP_ERROR(get_logger(),
                "Station '%s' and '%s' overlap in XY: waypoints not generated",
                stations_[i].c_str(), stations_[i+1].c_str()
            );
            continue;
        }
        nx /= norm;
        ny /= norm;

        // Force the normal to point away from the base (origin). Both stations
        // are equidistant from the base, so this asymmetric push is what makes
        // the arm route around the outer side of the shared workspace instead of
        // cutting across it between the two stations.
        if (nx*ref_x + ny*ref_y < 0.0){
            nx = -nx;
            ny = -ny;
        }

        // Two offsets = inner/outer arc, both on the outer side; fixed transit
        // height and orientation
        for (double offset : waypoint_offsets_){
            GetZone::Response wp;
            wp.position.x = ref_x + offset*nx;
            wp.position.y = ref_y + offset*ny;
            wp.position.z = waypoint_height_;
            wp.rpy.roll = 0.0;
            wp.rpy.pitch = 0.1085;
            wp.rpy.yaw = 0.0;
            wp.type = SceneObject::WAYPOINT;

            string name = "wp" + to_string(wp_index++);
            zones_[name] = wp;
            pair_wps.push_back(name);

            RCLCPP_INFO(get_logger(), "Generated waypoint '%s' at (%.3f, %.3f, %.3f)",
                name.c_str(), wp.position.x, wp.position.y, wp.position.z);
        }

        // Chain the pair into the graph: station_i <-> wp <-> station_{i+1}.
        for (const auto& wp_name : pair_wps){
            arcs_.emplace_back(stations_[i], wp_name);
            arcs_.emplace_back(wp_name, stations_[i+1]);
        }
    }
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
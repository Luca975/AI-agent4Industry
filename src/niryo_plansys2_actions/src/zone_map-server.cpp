#include <fstream>
#include <sstream>
#include "zone_map-server.hpp"



ZoneMapServer::ZoneMapServer() : Node("zone_map_server")
{
    declare_parameter("zones_file", "");
    declare_parameter("zone_thresholds", 0.15);
    declare_parameter("grasp_threshold", 0.05);
    declare_parameter("staleness_threshold", 1.0);
    declare_parameter("arm_name","arm_1");
    declare_parameter("class_to_type", vector<string>{});

    string csv_path = get_parameter("zones_file").as_string();
    zone_thresholds = get_parameter("zone_thresholds").as_double();
    grasp_threshold_ = get_parameter("grasp_threshold").as_double();
    staleness_threshold_ = get_parameter("staleness_threshold").as_double();
    arm_name_ = get_parameter("arm_name").as_string();

    const vector<string> class_entries = get_parameter("class_to_type").as_string_array();
    for (const auto& entry : class_entries){
        auto sep = entry.find(':');
        if (sep == string::npos){
            RCLCPP_ERROR(get_logger(), "Malformed class_to_type entry: '%s'", entry.c_str());
            continue;
        }
        class_to_type_[entry.substr(0,sep)] = entry.substr(sep + 1);
    }

    read_zones(csv_path);
    
    last_scene_ = Time(0,0, get_clock()->get_clock_type());
    last_arm_ = Time(0,0, get_clock()->get_clock_type());

    gripper_closed_ = false;
    tool_received_ = false;

    scene_sub_ = create_subscription<EnvScene>(
        "/env/scene",10,
        bind(&ZoneMapServer::on_scene, this, placeholders::_1)
    );

    QoS tool_qos(1);
    tool_qos.transient_local();
    tool_sub_ = create_subscription<ToolStatus>(
        "/arm_1/tool_status", tool_qos,
        bind(&ZoneMapServer::on_tool_status, this, placeholders::_1)
    );
    
    // TODO: verify the driver's QoS
    arm_sub_ = create_subscription<RobotState>(
        "/arm_1/niryo_robot/robot_state", SensorDataQoS(),
        bind(&ZoneMapServer::on_robot_state, this, placeholders::_1)
    );

    service_ = create_service<GetZone>(
        "/zone_map_server/get_zone",
        bind(&ZoneMapServer::handle_request, this, placeholders::_1, placeholders::_2)
    );

    observe_service_ = create_service<ObserveScene>(
        "/zone_map_server/observe_scene",
        bind(&ZoneMapServer::handle_observe_req, this, placeholders::_1, placeholders::_2)
    );
}


void ZoneMapServer::read_zones(const string& filename)
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

        getline(ss,name,',');
        getline(ss,type,',');
        ss >> x >> sep >> y >> sep >> z >> sep >> r >> sep >> p >> sep >> yaw;

        //Only the areas live in the config: they are a static map
        if(type != SceneObject::AREA){
            RCLCPP_WARN(get_logger(),
                "Ignoring non-area row '%s': objects come from /env/scene",
                name.c_str());
            continue;
        }
        
        GetZone::Response response;
        response.position.x = x;
        response.position.y = y;
        response.position.z = z;
        response.rpy.roll = r;
        response.rpy.pitch = p;
        response.rpy.yaw = yaw;

        zones_[name] = response;
        
    }
}

void ZoneMapServer::on_scene(const EnvScene::SharedPtr msg)
{
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

        item.support = obj.pose.position;
        item.support.z = obj.pose.position.z - obj.size.z / 2.0;
        fresh[obj.id] = item;
    }

    objects_ = fresh;
    last_scene_ = now();
}

void ZoneMapServer::on_tool_status(const ToolStatus::SharedPtr msg)
{
    gripper_closed_ = msg->closed;
    tool_received_=true;
}
void ZoneMapServer::on_robot_state(const RobotState::SharedPtr msg)
{
    arm_position_ = msg->position;
    last_arm_ = now();
}

string ZoneMapServer::resolve_zone(const geometry_msgs::msg::Point& p) const
{
    double best_dist = numeric_limits<double>::max();
    string best_zone = "";

    for(const auto& [zone_name, zone] : zones_){
        
        double dx = p.x - zone.position.x;
        double dy = p.y - zone.position.y;
        double dz = p.z - zone.position.z;
        double dist = sqrt(dx*dx + dy*dy + dz*dz);

        if(dist < best_dist){
            best_dist = dist;
            best_zone = zone_name;
        }
    }
    
    return (best_dist <= zone_thresholds) ? best_zone : "";
}

string ZoneMapServer::resolve_held() const
{
    if (!gripper_closed_)
    {
        return "";
    }
    
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

    if (held.empty()){
        RCLCPP_WARN(get_logger(), "Gripper is closed but no piece is within %.3f m of it",
        grasp_threshold_);
    }

    return held;
}

string ZoneMapServer::check_freshness() const
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

void ZoneMapServer::handle_request(const shared_ptr<GetZone::Request> request, shared_ptr<GetZone::Response> response)
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

void ZoneMapServer::handle_observe_req(const shared_ptr<ObserveScene::Request> request, shared_ptr<ObserveScene::Response> response)
{
    (void)request;

    
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

        obj.location = obj.held ? "" : resolve_zone(item.support);
        if (obj.location.empty() && !obj.held){
            RCLCPP_WARN(get_logger(), "Locatable '%s' is outside every zone", name.c_str());
        }

        response->objects.push_back(obj);
    }

    SceneObject arm;
    arm.name = arm_name_;
    arm.type = SceneObject::ROBOT;
    arm.held = false;
    arm.color = "";
    const string arm_zone = resolve_zone(arm_position_);
    arm.location = arm_zone.empty() ? SOME_PLACE : arm_zone;

    RCLCPP_DEBUG(get_logger(),"Arm '%s' location: '%s'",arm_name_.c_str(), arm.location.c_str());

    response -> objects.push_back(arm);

    for (const auto& [zone_name, zone] : zones_){
        (void)zone;
        SceneObject obj;
        obj.name = zone_name;
        obj.type = SceneObject::AREA;
        obj.location = "";
        obj.held = false;
        obj.color = "";

        response->objects.push_back(obj);
    }

    response->success = true;
    response->error_info = "";
}

int main(int argc, char **argv)
{
    init(argc, argv);
    auto node = make_shared<ZoneMapServer>();
    spin(node);
    shutdown();
    return 0;
}
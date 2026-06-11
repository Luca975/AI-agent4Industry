#include <fstream>
#include <sstream>
#include "zone_map-server.hpp"



ZoneMapServer::ZoneMapServer() : Node("zone_map_server")
{
    declare_parameter("zones_file", "");
    declare_parameter("zone_thresholds", 0.15);

    string csv_path = get_parameter("zones_file").as_string();
    zone_thresholds = get_parameter("zone_thresholds").as_double();

    read_scene(csv_path);
    
    service_ = create_service<GetZone>(
        "get_zone",
        bind(&ZoneMapServer::handle_request, this, placeholders::_1, placeholders::_2)
    );

    observe_service_ = create_service<ObserveScene>(
        "observe_scene",
        bind(&ZoneMapServer::handle_observe_req, this, placeholders::_1, placeholders::_2)
    );
}


void ZoneMapServer::read_scene(const string& filename)
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

        if (type == SceneObject::AREA){

            GetZone::Response response;
            response.position.x = x;
            response.position.y = y;
            response.position.z = z;
            response.rpy.roll = r;
            response.rpy.pitch = p;
            response.rpy.yaw = yaw;

            zones_[name] = response;
        }
        else {
            SceneItem item;
            item.type = type;
            item.position.x = x;
            item.position.y = y;
            item.position.z = z;

            objects_[name] = item;
        }
    }
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

    for(const auto& [name, item] : objects_){
        SceneObject obj;
        obj.name = name;
        obj.type = item.type;
        obj.location = "";
        
        double best_dist = numeric_limits<double>::max();
        string best_zone = "";

        for(const auto& [zone_name, zone] : zones_){
            
            double dx = item.position.x - zone.position.x;
            double dy = item.position.y - zone.position.y;
            double dz = item.position.z - zone.position.z;
            double dist = sqrt(dx*dx + dy*dy + dz*dz);

            if(dist < best_dist){
                best_dist = dist;
                best_zone = zone_name;
            }
        }

        if(best_dist <= zone_thresholds){
            obj.location = best_zone;
        }
        else{
            RCLCPP_WARN(get_logger(),
                "Locatable '%s' is outside every zone (nearest %.3f m > threshold %.3f m)",
                name.c_str(), best_dist, zone_thresholds);
        }
        
        response->objects.push_back(obj);
    }

    for(const auto& [zone_name, zone] : zones_){

        (void)zone;
        SceneObject obj;
        obj.name=zone_name;
        obj.type=SceneObject::AREA;
        obj.location="";

        response->objects.push_back(obj);
    }

    response->success = true;
}

int main(int argc, char **argv)
{
    init(argc, argv);
    auto node = make_shared<ZoneMapServer>();
    spin(node);
    shutdown();
    return 0;
}
#include <fstream>
#include <sstream>
#include "zone_map-server.hpp"



ZoneMapServer::ZoneMapServer() : Node("zone_map_server")
{
    declare_parameter("zones_file", "");
    string csv_path = get_parameter("zones_file").as_string();
    read_zones(csv_path);
    
    service_ = create_service<GetZone>(
        "get_zone",
        bind(&ZoneMapServer::handle_request, this, placeholders::_1, placeholders::_2)
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
        string name;
        double x,y,z,r,p,yaw;
        char sep;

        getline(ss,name,',');
        ss >> x >> sep >> y >> sep >> z >> sep >> r >> sep >> p >> sep >> yaw;

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

int main(int argc, char **argv)
{
    init(argc, argv);
    auto node = make_shared<ZoneMapServer>();
    spin(node);
    shutdown();
    return 0;
}
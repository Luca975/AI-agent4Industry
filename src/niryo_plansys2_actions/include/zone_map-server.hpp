#pragma once

#include "rclcpp/rclcpp.hpp"
#include "niryo_plansys2_interfaces/srv/get_zone.hpp"

#include <string>
#include <map>

using namespace rclcpp;
using namespace std;

using GetZone = niryo_plansys2_interfaces::srv::GetZone;


class ZoneMapServer : public Node
{
    public:
        ZoneMapServer();

    private:
        void read_zones(const string& filename);
        void handle_request(const shared_ptr<GetZone::Request> request, shared_ptr<GetZone::Response> response);

        Service<GetZone>::SharedPtr service_;
        map<string, GetZone::Response> zones_;
};
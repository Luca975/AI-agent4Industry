#pragma once

#include "rclcpp/rclcpp.hpp"
#include "niryo_plansys2_interfaces/srv/get_zone.hpp"
#include "niryo_plansys2_interfaces/srv/observe_scene.hpp"
#include "niryo_plansys2_interfaces/msg/scene_object.hpp"
#include "geometry_msgs/msg/point.hpp"

#include <string>
#include <map>

using namespace rclcpp;
using namespace std;

using GetZone = niryo_plansys2_interfaces::srv::GetZone;
using ObserveScene = niryo_plansys2_interfaces::srv::ObserveScene;
using SceneObject = niryo_plansys2_interfaces::msg::SceneObject;


struct SceneItem{
    string type;
    geometry_msgs::msg::Point position;
};


class ZoneMapServer : public Node
{
    public:
        ZoneMapServer();

    private:
        void read_scene(const string& filename);
        void handle_request(const shared_ptr<GetZone::Request> request, shared_ptr<GetZone::Response> response);
        void handle_observe_req(const shared_ptr<ObserveScene::Request> request, shared_ptr<ObserveScene::Response> response);

        Service<GetZone>::SharedPtr service_;
        Service<ObserveScene>::SharedPtr observe_service_;

        map<string, GetZone::Response> zones_;
        map<string, SceneItem> objects_;
        double zone_thresholds;
};
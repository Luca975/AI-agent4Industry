#pragma once

#include "rclcpp/rclcpp.hpp"
#include "niryo_plansys2_interfaces/srv/get_zone.hpp"
#include "niryo_plansys2_interfaces/srv/observe_scene.hpp"
#include "niryo_plansys2_interfaces/msg/scene_object.hpp"
#include "niryo_env_interfaces/msg/env_scene.hpp"
#include "niryo_env_interfaces/msg/tool_status.hpp"
#include "niryo_ned_ros2_interfaces/msg/robot_state.hpp"
#include "geometry_msgs/msg/point.hpp"

#include <string>
#include <map>

using namespace rclcpp;
using namespace std;

using GetZone = niryo_plansys2_interfaces::srv::GetZone;
using ObserveScene = niryo_plansys2_interfaces::srv::ObserveScene;
using SceneObject = niryo_plansys2_interfaces::msg::SceneObject;
using EnvScene = niryo_env_interfaces::msg::EnvScene;
using ToolStatus = niryo_env_interfaces::msg::ToolStatus;
using RobotState = niryo_ned_ros2_interfaces::msg::RobotState;


struct SceneItem{
    string type;
    string color;
    geometry_msgs::msg::Point support; //bottom of the object
    geometry_msgs::msg::Point center;
};


class ZoneMapServer : public Node
{
    public:
        ZoneMapServer();

    private:
        void read_zones(const string& filename);

        void on_scene(const EnvScene::SharedPtr msg);
        void on_tool_status(const ToolStatus::SharedPtr msg);
        void on_robot_state(const RobotState::SharedPtr msg);


        void handle_request(const shared_ptr<GetZone::Request> request, shared_ptr<GetZone::Response> response);
        void handle_observe_req(const shared_ptr<ObserveScene::Request> request, shared_ptr<ObserveScene::Response> response);

        string resolve_zone(const geometry_msgs::msg::Point& p) const;
        string resolve_held() const;
        string check_freshness() const;

        Service<GetZone>::SharedPtr service_;
        Service<ObserveScene>::SharedPtr observe_service_;

        Subscription<EnvScene>::SharedPtr scene_sub_;
        Subscription<ToolStatus>::SharedPtr tool_sub_;
        Subscription<RobotState>::SharedPtr arm_sub_;

        map<string, GetZone::Response> zones_;
        map<string, SceneItem> objects_;
        map<string, string> class_to_type_;

        geometry_msgs::msg::Point arm_position_;
        bool gripper_closed_;

        Time last_scene_;
        Time last_arm_;
        bool tool_received_;


        string arm_name_;
        double zone_thresholds;
        double grasp_threshold_;
        double staleness_threshold_;
};
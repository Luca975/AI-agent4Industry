#pragma once

#include "rclcpp/rclcpp.hpp"
#include "niryo_world_interfaces/srv/get_zone.hpp"
#include "niryo_world_interfaces/srv/observe_scene.hpp"
#include "niryo_world_interfaces/msg/scene_object.hpp"
#include "niryo_world_interfaces/msg/scene_path.hpp"
#include "niryo_world_interfaces/srv/check_path.hpp"
#include "niryo_world_interfaces/srv/check_node.hpp"

#include "niryo_env_interfaces/msg/env_scene.hpp"
#include "niryo_env_interfaces/msg/tool_status.hpp"
#include "niryo_ned_ros2_interfaces/msg/robot_state.hpp"
#include "geometry_msgs/msg/point.hpp"

#include <string>
#include <map>
#include <vector>
#include <utility>
#include <algorithm>

using namespace rclcpp;
using namespace std;

using GetZone = niryo_world_interfaces::srv::GetZone;
using ObserveScene = niryo_world_interfaces::srv::ObserveScene;
using SceneObject = niryo_world_interfaces::msg::SceneObject;
using ScenePath = niryo_world_interfaces::msg::ScenePath;
using CheckPath = niryo_world_interfaces::srv::CheckPath;
using CheckNode = niryo_world_interfaces::srv::CheckNode;
using EnvScene = niryo_env_interfaces::msg::EnvScene;
using ToolStatus = niryo_env_interfaces::msg::ToolStatus;
using RobotState = niryo_ned_ros2_interfaces::msg::RobotState;


struct SceneItem{
    string type;
    string color;
    geometry_msgs::msg::Point support; //bottom of the object
    geometry_msgs::msg::Point center;
};


class WorldModelServer : public Node
{
    public:
        WorldModelServer();

    private:
        void read_zones(const string& filename);
        void generate_waypoints();

        void on_scene(const EnvScene::SharedPtr msg);
        void on_tool_status(const ToolStatus::SharedPtr msg);
        void on_robot_state(const RobotState::SharedPtr msg);

        void build_arcs();
        bool is_path_clear(const string& from, const string& to) const;
        bool is_node_clear(const string& node) const;

        void handle_request(const shared_ptr<GetZone::Request> request, shared_ptr<GetZone::Response> response);
        void handle_observe_req(const shared_ptr<ObserveScene::Request> request, shared_ptr<ObserveScene::Response> response);
        void handle_check_path(const shared_ptr<CheckPath::Request> request, shared_ptr<CheckPath::Response> response);
        void handle_check_node(const shared_ptr<CheckNode::Request> request, shared_ptr<CheckNode::Response> response);
        
        string resolve_zone(const geometry_msgs::msg::Point& p, const string& locatable_type) const;
        string resolve_held() const;
        string check_freshness() const;

        Service<GetZone>::SharedPtr service_;
        Service<ObserveScene>::SharedPtr observe_service_;
        Service<CheckPath>::SharedPtr check_path_service_;
        Service<CheckNode>::SharedPtr check_node_service_;

        Subscription<EnvScene>::SharedPtr scene_sub_;
        Subscription<ToolStatus>::SharedPtr tool_sub_;
        Subscription<RobotState>::SharedPtr arm_sub_;

        map<string, GetZone::Response> zones_;
        vector<string> stations_;
        vector<pair<string, string>> arcs_;
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
        vector<double> waypoint_offsets_;
        double waypoint_height_;
        double human_radius_;
        double path_clearance_;

        /*This is used when the arm is in none fo the real areas*/
        static constexpr const char* SOME_PLACE = "some_place";

        static constexpr const char* HOME_NODE = "home";
};
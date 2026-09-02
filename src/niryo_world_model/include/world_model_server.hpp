/**
 *  @file world_model_server.hpp
 *   @brief The node turns the raw perception stream into the facts
 *       the planning layer needs.
 *
 *       The server owns a *static* topological map (areas + auto-generated waypoints,
 *       read once from a CSV at startup) and fuse it with the *live* perception, gripper
 *       and arm-state streams. It exposes four services:
 *       - get_zone: the pose (x,y,z,roll,pitch,yaw) of a named zone
 *       - observe_scene: a full symbolic snapshot ready to be transcribed into a PDDL :init section.
 *       - check_path: is the arc *from->to* currently free of humans?
 *       - check_node: is a single node currently free of humans?
 *
 *       check_path/check_node are the ones polled at 10 Hz by the safety monitor;
 *       observe_scene is called once per planning by the agent layer.
 *
 *      The node never commands the arm. It is a pure source of fact
 */

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

/** 
 *      @brief One detected object in the live scene, in the internal representation.
 *      Populated from an EnvObject in on_scene(). @ref support is the point actually used
 *      for zone resolution of pieces (a piece "is in " the area its base rests on, not the one its centroid floats over), 
 *      while @ref center is used for grasp resolution against the arm tip.
*/

struct SceneItem{
    string type;                        ///< Semantic type (SceneObject::PIECE / HUMAN / ...) mapped from class_id.
    string color;
    geometry_msgs::msg::Point support;  ///< Bottom-center of the object (centered with z lowered by half the height)
    geometry_msgs::msg::Point center;   ///< Centoid of the object, as reported by perception
};


class WorldModelServer : public Node
{
    public:
        WorldModelServer();

    private:

        // --- Startup: build the static topological map -----------------------
        
        /**
         * @brief Load zones from a CSV file into @ref zones_.
         * Row format: name,type,x,y,z,roll,pitch,yaw. Only AREA and WAYPOINT
         * rows are kept (everything else is a runtime object and comes from
         * perception, not config); AREA rows are additionally recorded in @ref stations_ in file order.
         * @param filename Absolute path to the zones CSV.
         */
        void read_zones(const string& filename);

        /**
         * @brief Synthesize a pair of via-waypoints between each consecutive
         *        station pair and add the corresponding arcs.
         *
         * For stations A,B the waypoints sit on the perpendicular bisector of
         * AB, pushed to the *outer* side (away from the robot base) so the arm
         * routes around the shared workspace instead of across it. Both offsets
         * in @ref waypoint_offsets_ (inner/outer arc) are placed at fixed
         * @ref waypoint_height_. Requires at least two stations.
         */        
        void generate_waypoints();

        /**
         * @brief Connect HOME_NODE to every waypoint, completing the graph.
         *
         * Must run after generate_waypoints() (the waypoints must already exist
         * in @ref zones_). Together with the station<->waypoint arcs added by
         * generate_waypoints(), this yields the full navigable topology.
         */
        void build_arcs();

        // --- Live streams ----------------------------------------------------

        /**
         * @brief Rebuild @ref objects_ from a fresh perception frame.
         * 
         * Objects whose class_id is not in @ref class_to_type_ are dropped with
         * a warning. Stamps @ref last_scene_ so freshness can be checked later.
         * @param msg Latest EnvScene from /env/scene.
         */
        void on_scene(const EnvScene::SharedPtr msg);

        /**
         * @brief Cache the gripper open/closed state
         * @param msg Latest ToolStatus.
         */
        void on_tool_status(const ToolStatus::SharedPtr msg);

        /**
         * @brief Cache the arm cartesian position and stamp @ref last_arm_.
         * @param msg Latest RobotState from the driver.
         */
        void on_robot_state(const RobotState::SharedPtr msg);


        // --- Geometry/occupancy queries ----------------------------------------

        /**
         * @brief Is the arc from->to free of humans right now?
         * 
         * A human blocks the arc if its XY distance to the segment (point-to-segment, parameter clamped to [0,1])
         * is below @ref path_clearance_. @return false if either node is unknown or any humans obstructs it.
         */
        bool is_path_clear(const string& from, const string& to) const;

        /**
         * @brief Is the node free of humans right now?
         * 
         * A human occupies the node if its XY distance to the node is within @ref human_radius_.
         * @return false if the node is uknown or any human occupies it.
         */
        bool is_node_clear(const string& node) const;

        // --- Service handlers --------------------------------------------------------------------------
        /**
         * @brief get_zone handler: return the stored pose/type of the named zone.
         * Sets success=false if the zone is unknown.
         */
        void handle_request(const shared_ptr<GetZone::Request> request, shared_ptr<GetZone::Response> response);
        
        /**
         * @brief observe_scene handler: emits a full symbolic snapshot.
         */
        void handle_observe_req(const shared_ptr<ObserveScene::Request> request, shared_ptr<ObserveScene::Response> response);
        
        void handle_check_path(const shared_ptr<CheckPath::Request> request, shared_ptr<CheckPath::Response> response);
        
        void handle_check_node(const shared_ptr<CheckNode::Request> request, shared_ptr<CheckNode::Response> response);
        
        // --- Resolution helpers -------------------------------------------------------------------

        /**
         * @brief Nearest zone to a point, within a type-dependent threshold.
         * 
         * A PIECE resolves againts AREAs only; a HUMAN resolves in 2D (z ignored) within @ref human_radius_; everything else resolves in 3D
         * within @ref zone_threshold_.
         * @param p Query point (for a piece, its support point).
         * @param locatable_type Semantic type driving the matching rule.
         * @return Zone name, or "" if nothing is within threshold.
         */
        string resolve_zone(const geometry_msgs::msg::Point& p, const string& locatable_type) const;

        /**
         * @brief Which piece, if any, the gripper is currently holding.
         * 
         * Empty if the gripper is open. Otherwise the nearest PIECE within @ref gras_threshold_
         * of the arm tip; "" (with a warning) if the gripper is closed but no piece is close enough.
         */
        string resolve_held() const;

        /**
         * @brief Freshness gate for observe_scene.
         * 
         * @return "" if scene and arms streams are both present and younger than @ref staleness_threshold_;
         * otherwise a human-readable reason. The tool state is deliberately excluded (it is an event, not a stream: an old-but-valid pick
         * must not look stale).
         */
        string check_freshness() const;

        // --- Services -----------------------------------

        Service<GetZone>::SharedPtr service_;               ///< /world_model_server/get_zone
        Service<ObserveScene>::SharedPtr observe_service_;  ///< /world_model_server/observe_scene
        Service<CheckPath>::SharedPtr check_path_service_;  ///< /world_model_server/check_path
        Service<CheckNode>::SharedPtr check_node_service_;  ///< /world_model_server/check_node

        // -- Subscriptions --------------------------------

        Subscription<EnvScene>::SharedPtr scene_sub_;       ///< /env/scene (perception)
        Subscription<ToolStatus>::SharedPtr tool_sub_;      ///< /arm_1/tool_status
        Subscription<RobotState>::SharedPtr arm_sub_;       ///< /arm_1/niryo_robot/robot_state (arm pose)

        // --- Static map (built at startup, never mutated afterwards) ---------------
        map<string, GetZone::Response> zones_;              ///< Name -> zone pose+type. Reuses GetZone::Response as the storage record. 
        vector<string> stations_;                           ///< AREA names in CSV order (input to waypoint pairing).
        vector<pair<string, string>> arcs_;                 ///< Undirected edges, stored once; emitted both ways in observe_scene.

        // --- Live state ------------------------------------------------------------
        map<string, SceneItem> objects_;                    ///< Latest detected objects, keyed by perception id.
        map<string, string> class_to_type_;                 ///< class_id -> semantic type, parsed from the class_to_type param.

        geometry_msgs::msg::Point arm_position_;            ///< Latest arm cartesian position.
        bool gripper_closed_;                               ///< Latest gripper state.

        // --- Freshness bookkeeping ------------------------------------------------
        Time last_scene_;                                   ///< Stamp of the last /env/scene frame (0 = none yet).
        Time last_arm_;                                     ///< Stamp of the last arm state (0 = none yet).
        bool tool_received_;                                ///< Whether any ToolStatus has arrived (gripper assumed open until then).

        // --- Configuration parameters -----------------------------------------
    string arm_name_;                                       ///< Symbolic name emitted for the arm in observe_scene
        double zone_thresholds;                             ///< Max distance for a generic locatable to resolve to a zone.
        double grasp_threshold_;                            ///< Max arm-to-piece distance to consider a piece held
        double staleness_threshold_;                        ///< Max stream age (s) before observe_scene refuses.
        vector<double> waypoint_offsets_;                   ///< Perpendicular offsets (inner/outer arc) for generated waypoints.
        double waypoint_height_;                            ///< Fixed z of generated waypoints.
        double human_radius_;                               ///< Occupancy radius of a human (node and human-zone matching).
        double path_clearance_;                             ///< Min human-to-segment- distance for an arc to count as a clear.

        ///Fallback location reported for the arm when it is in none of the real zones
        static constexpr const char* SOME_PLACE = "some_place";

        /// Central node every waypoint is connected to; also the arm rest's position.
        static constexpr const char* HOME_NODE = "home";
};
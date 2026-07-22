(define (problem test) (:domain gazebo_world)
(:objects 
    arm_1 - robot
    workspace_1 conveyor - area
    circle_2 - piece
    wp1 wp2 home - waypoint
)

(:init
    (available arm_1)
    (at circle_2 workspace_1)
    (at arm_1 home)

    (clean home)
    (clean workspace_1)
    (clean conveyor)
    (clean wp1)
    (clean wp2)

    (free workspace_1)
    (free conveyor)
    (free wp1)
    (free wp2)

    (connected home wp1)      (connected wp1 home)
    (connected home wp2)      (connected wp2 home)
    (connected workspace_1 wp1) (connected wp1 workspace_1)
    (connected wp1 conveyor)  (connected conveyor wp1)
    (connected workspace_1 wp2) (connected wp2 workspace_1)
    (connected wp2 conveyor)  (connected conveyor wp2)

    (clean_path home wp1)      (clean_path wp1 home)
    (clean_path home wp2)      (clean_path wp2 home)
    (clean_path workspace_1 wp1) (clean_path wp1 workspace_1)
    (clean_path wp1 conveyor)  (clean_path conveyor wp1)
    (clean_path workspace_1 wp2) (clean_path wp2 workspace_1)
    (clean_path wp2 conveyor)  (clean_path conveyor wp2) 

)

(:goal 
    (at circle_2 conveyor)
)
)

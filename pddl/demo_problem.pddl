(define (problem test) (:domain gazebo_world)
(:objects 
    arm_1 - robot
    workspace_1 conveyor some_place - area
    red_cube - piece
)

(:init
    (available arm_1)
    (at red_cube workspace_1)
    (at arm_1 some_place)
    (clean workspace_1)
    (clean conveyor)
)

(:goal (and
    (at red_cube conveyor)
    )
)
)

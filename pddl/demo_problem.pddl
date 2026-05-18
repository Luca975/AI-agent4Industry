(define (problem test) (:domain gazebo_world)
(:objects 
    arm_1 - robot
    workspace_1 conveyor  some_place - area
    red_cube - piece
)

(:init
    ;todo: put the initial state's facts and numeric values here
    (available arm_1)
    (at red_cube workspace_1)
    (at arm_1 some_place)
)

(:goal (and
    (at red_cube conveyor)
    ;todo: put the goal condition here
))

;un-comment the following line if metric is needed
;(:metric minimize (???))
)

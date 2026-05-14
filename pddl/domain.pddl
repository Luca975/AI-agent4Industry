;Header and description
(define (domain gazebo_world)

(:requirements :strips :fluents :durative-actions :typing :negative-preconditions :equality)

(:types 
    object human robot - locatable
    area
)

; un-comment following line if constants are needed
;(:constants )

(:predicates
    (at ?x - locatable ?y - area)
    (available ?x - robot)
    (holding ?x - robot ?y - object)
    ;(clear ?x - area)
)


;(:functions todo: define numeric functions here)

;define actions here
(:action move
    :parameters (?x - robot ?y - area)
    :precondition (not (at ?x ?y))
    :effect (at ?x ?y)
)

(:action pick
    :parameters (?x - robot ?y - area ?z - object)
    :precondition (and (available ?x) (at ?x ?y) (at ?z ?y))
    :effect (and (not (available ?x)) (holding ?x ?z))
)

(:action place
    :parameters (?x - robot ?y - area ?z - object)
    :precondition (and (at ?x ?y) (holding ?x ?z))
    :effect (and (at ?z ?y) (available ?x) (not (holding ?x ?z)))
)

)
;Header and description
(define (domain gazebo_world)

(:requirements :strips :typing :negative-preconditions)

(:types 
    piece human robot - locatable
    area
)

; un-comment following line if constants are needed
;(:constants )

(:predicates
    (at ?x - locatable ?y - area)
    (available ?x - robot)
    (holding ?x - robot ?y - piece)
    ;(clear ?x - area)
)


;(:functions todo: define numeric functions here)

;define actions here
(:action move
    :parameters (?x - robot ?from - area ?to - area)
    :precondition (and (at ?x ?from) (not (at ?x ?to)))
    :effect (and (at ?x ?to) (not (at ?x ?from)))
)

(:action pick
    :parameters (?x - robot ?y - area ?z - piece)
    :precondition (and (available ?x) (at ?x ?y) (at ?z ?y))
    :effect (and (not (available ?x)) (holding ?x ?z))
)

(:action place
    :parameters (?x - robot ?y - area ?z - piece)
    :precondition (and (at ?x ?y) (holding ?x ?z))
    :effect (and (at ?z ?y) (available ?x) (not (holding ?x ?z)))
)

)
(define (domain gazebo_world)

(:requirements :strips :typing :durative-actions :equality)

(:types 
    piece human robot - locatable
    area
)

(:predicates
    (at ?x - locatable ?y - area)
    (available ?x - robot)
    (clean ?x - area)
    (holding ?x - robot ?y - piece)
)

(:durative-action move
    :parameters (?x - robot ?from - area ?to - area)
    :duration (= ?duration 5)
    :condition (and 
        (at start (and
                (at ?x ?from)
                (clean ?to)
            )
        )
    )
    :effect (and 
        (at start
            (not (at ?x ?from))
        )
        (at end (and
            (at ?x ?to)
            (not (clean ?to))
        ))
    )
)

(:durative-action pick
    :parameters (?x - robot ?y - area ?z - piece)
    :duration (= ?duration 5)
    :condition (and 
        (at start (and 
            (available ?x) 
            (at ?x ?y) 
            (at ?z ?y)
        ))
        (over all (and 
            (at ?x ?y)
        ))
        (at end 
            (at ?x ?y)
        )
    )
    :effect (and 
        (at end (and 
            (not(available ?x))
            (holding ?x ?z)
            (at ?x ?y)
            (not(at ?z ?y))
        ))
    )
)

(:durative-action place
    :parameters (?x - robot ?y - area ?z - piece)
    :duration (= ?duration 5)
    :condition (and 
        (at start (and 
            (holding ?x ?z)
            (at ?x ?y)
        ))
        (over all 
            (at ?x ?y) 
        )
        (at end
            (at ?x ?y) 
        )
    )
    :effect (and
        (at end (and 
            (at ?x ?y)
            (at ?z ?y)
            (available ?x)
            (not(holding ?x ?z))
        ))
    )
)

)
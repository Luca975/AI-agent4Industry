(define (domain gazebo_world)

(:requirements :strips :typing :durative-actions)

(:types 
    piece obstacle robot - locatable
    human - obstacle
    waypoint area - location
)

(:predicates
    (at ?x - locatable ?y - location)
    (available ?x - robot)
    (holding ?x - robot ?y - piece)
    (clean ?x - location)
    (clean_path ?x - location ?y - location)
    (free ?l - location)
    (connected ?a - location ?b - location)
)

(:durative-action move
    :parameters (?x - robot ?from - location ?to - location)
    :duration (= ?duration 5)
    :condition (and
                (at start (and
                            (at ?x ?from)
                            (connected ?from ?to)
                            (clean_path ?from ?to)
                            (clean ?to)
                            (free ?to)
                            )
                )
                (over all (and
                            (clean_path ?from ?to)
                            (clean ?to)
                        ) 
                )
        )
    :effect (and 
                (at start (and
                    (not (at ?x ?from))
                    (not (free ?to))
                    )
                )
                (at end (and
                    (at ?x ?to)
                    (free ?from)
                    )
                )
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
                    (clean ?y)
                ))
                (over all (and 
                    (at ?x ?y)
                    (clean ?y)
                ))
                (at end 
                    (at ?x ?y)
                )
            )
    :effect    (at end (and 
                    (not(available ?x))
                    (holding ?x ?z)
                    (at ?x ?y)
                    (not(at ?z ?y))
                    )
                )
)

(:durative-action place
    :parameters (?x - robot ?y - area ?z - piece)
    :duration (= ?duration 5)
    :condition (and 
                (at start (and 
                    (holding ?x ?z)
                    (at ?x ?y)
                    (clean ?y)
                    )
                )
                (over all (and
                    (at ?x ?y)
                    (clean ?y)
                    ) 
                )
                (at end
                    (at ?x ?y) 
                )
    )
    :effect (at end (and 
                (at ?x ?y)
                (at ?z ?y)
                (available ?x)
                (not(holding ?x ?z))
            )
        )
)

)
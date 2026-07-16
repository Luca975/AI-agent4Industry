string id

# What the detector recognise (cube, person)
string class_id
float64 score

# Empty when does not apply to the class (e.g. a person)
string color

# Pose of the object CENTRE
geometry_msgs/Pose pose

# Extent of the object along the axes of its own (oriented) pose
geometry_msgs/Vector3 size
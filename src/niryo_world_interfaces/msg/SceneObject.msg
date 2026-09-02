# Allowed values for the 'type' field
string PIECE=piece
string HUMAN=human
string ROBOT=robot
string AREA=area
string WAYPOINT=waypoint

string name
string type
string location     # node the object rests on; empty for AREA/WAYPOINT nodes and for a held piece
bool held           # a piece with held = true is not AT any area, it is in the gripper
string color

#the location field is empty for the AREA and WAYPOINT type
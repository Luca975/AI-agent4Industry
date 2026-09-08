#Safety alert raised by safe_monitor on /safety_alert, consumed by the MoveAction
#performer. Published only when the verdict changes: the performer
#gets one message when the invariant breaks and one when it clears, not a stream.

string action_full_name     #the PlanSys2 action instance this alert refers to
bool blocked                #true: obstacle on the watched arc/node; false: back to clear
string target               #arc "from->to" (move) or node (pick/place); for logging
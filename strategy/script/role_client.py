#! /usr/bin/env python

from __future__ import print_function
import rospy

# Brings in the SimpleActionClient
import actionlib

# Brings in the messages used by the fibonacci action, including the
# goal message and the result message.
import actionlib_tutorials.msg
import strategy.msg
from role_selector import RoleSelector

def fibonacci_client():
    print("in")
    rs = RoleSelector()
    print("passing")
    r = RoleSelector.PassingTo("/robot2")
    print("end")
    # myRole = RoleSelector.MyRole(rospy.get_namespace())
    # print(myRole)
    # print(RoleSelector.GetState("/robot2"))
    # print(RoleSelector.GetState("/robot3"))
    return r

if __name__ == '__main__':
    try:
        # Initializes a rospy node so that the SimpleActionClient can
        # publish and subscribe over ROS.
        rospy.init_node('fibonacci_client_py')
        result = fibonacci_client()
        print("Result: ", result)
    except rospy.ROSInterruptException:
        print("program interrupted before completion", file=sys.stderr)
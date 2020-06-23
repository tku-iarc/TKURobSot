#include "obstacle.h"

void SigintHandler(int sig)
{
    ROS_INFO("shutting down!");
    ros::shutdown();
}

int main(int argc, char **argv)
{
    ros::init(argc, argv, "obstacle");
    ros::NodeHandle h_node;
    signal(SIGINT, SigintHandler);
    Vision cam("camera/image_raw");
    
    ros::Rate loop_rate(200);
    while(ros::ok()){
        ros::spinOnce();
        loop_rate.sleep();
    }
    ROS_INFO("Node exit");
    printf("Process exit\n");
    return 0;
}

#include "nodehandle.h"

class Vision : protected NodeHandle
{
  public:
    Vision();
    Vision(string topic);
    ~Vision();
    void release();
    cv::Mat Black_Item(const cv::Mat iframe);
    
  private:
    ros::NodeHandle nh;
    ros::Subscriber image_sub;
    void imageCb(const sensor_msgs::ImageConstPtr &msg);
    void Mark_point(Mat &frame_, deque<int> &find_point, int distance, int angle, int x, int y, int &size, int color);
    void object_compare(DetectedObject &FIND_Item, int distance, int angle);
    void find_around_black(Mat &frame_, deque<int> &find_point, int distance, int angle, int &size, int color);
    void draw_ellipse(Mat &frame_, DetectedObject &obj_, int color);
    void draw_Line(Mat &frame_, int obj_distance_max, int obj_distance_min, int obj_angle, int color);
    Mat convertTo3Channels(const Mat &binImg);
    Mat ColorMoldel(Mat iframe, vector<int> HSV);
    double Rate();
    double FrameRate;
    //==========================================
    cv::Mat Source;
    cv::Mat threshold;
    cv::Mat monitor;
};

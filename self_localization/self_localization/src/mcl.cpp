#include "mcl.h"
#include "util.hpp"
#include <fstream>
#include <iostream>
#include <cstring>
#include <ros/package.h>
#include <opencv2/opencv.hpp>
#include "fMatrix/fVector.h"

#define N_PARTICLE 600
#define TO_RAD M_PI/180.0

#define FIELD_WIDTH 600
#define FIELD_HEIGHT 400

#define XLINE1 300
#define XLINE2 XLINE1-40
#define XLINE3 XLINE1-75
#define XLINE4 0
#define XLINE5 -(XLINE3)
#define XLINE6 -(XLINE2)
#define XLINE7 -(XLINE1)
#define XLINE8 75
#define XLINE9 -XLINE8

#define YLINE1 200
#define YLINE2 100
#define YLINE3 80
#define YLINE4 -(YLINE3)
#define YLINE5 -(YLINE2)
#define YLINE6 -(YLINE1)

#define CENTER_RADIUS 60
#define CENTER_RADIUS2 25

#define DISTANCE_MATRIX_WIDTH 700
#define DISTANCE_MATRIX_HEIGHT 500
// for qrc
//#include <QtCore>
//#include <QString>
//#include <QResource>
//#include <QFileInfo>
using namespace std;
using namespace cv;
typedef unsigned char BYTE;
MCL::MCL() :
  xvar(10), yvar(10), wvar(5),
  cmps(0),
  w_fast(0.0), w_slow(0.0),
  a_fast(1.), a_slow(0.0005),
  wcmps(0.1), wvision(1.-wcmps)
{
  std::random_device x_rd, y_rd, w_rd;
  std::uniform_real_distribution<double> x_rgen(-300,300), y_rgen(-200,200), w_rgen(0.0,360.0);
  for(int i=0; i<N_PARTICLE; i++)
  {
    particles.push_back(Particle(x_rgen(x_rd),y_rgen(y_rd),w_rgen(w_rd),wvision/N_PARTICLE,wcmps/N_PARTICLE,1.0/N_PARTICLE));
  }
}

void MCL::setAugmentParam(double a_fast, double a_slow)
{
  this->a_fast = a_fast;
  this->a_slow = a_slow;
  this->w_fast = 0.0;
  this->w_slow = 0.0;
}

void MCL::setCmpsWeight(double w)
{
  this->wcmps = w;
  this->wvision = 1. - wcmps;
}

void MCL::updateMotion(double vx, double vy, double dw)
{
  utility::timer timer;
  mutex.lock();
  static std::random_device xrd, yrd, wrd;
  static std::normal_distribution<> xgen(0.0,xvar), ygen(0.0,yvar), wgen(0.0,wvar);
  for(auto& p : particles)
  {
    double c = cos(w(p)*TO_RAD);
    double s = sin(w(p)*TO_RAD);
    double dx = c*vx+s*vy;
    double dy = -s*vx+c*vy;
    double static_noise_x = xgen(xrd)/5.0;
    double static_noise_y = ygen(yrd)/5.0;
    double static_noise_w = wgen(wrd)/1.0;
    double dynamic_noise_x = fabs(dx)*xgen(xrd)/5.0;
    double dynamic_noise_y = fabs(dy)*ygen(yrd)/5.0;
    double dynamic_noise_w = fabs(dw)*wgen(wrd)/3.0;
    double x_yterm = fabs(dy)*xgen(xrd)/30.0; // dynamic noise on x-direction because of y motion
    double x_wterm = fabs(dw)*xgen(xrd)/30.0; // dynamic noise on x-direction because of w motion
    double y_xterm = fabs(dx)*ygen(yrd)/30.0; // dynamic noise on y-direction because of x motion
    double y_wterm = fabs(dw)*ygen(yrd)/30.0; // dynamic noise on y-direction because of w motion
    double w_xterm = fabs(dx)*wgen(wrd)/2.0; // dynamic noise on w-direction because of x motion
    double w_yterm = fabs(dy)*wgen(wrd)/2.0; // dynamic noise on w-direction because of y motion
    x(p) += dx+static_noise_x+dynamic_noise_x+x_yterm+x_wterm;
    y(p) += dy+static_noise_y+dynamic_noise_y+y_xterm+y_wterm;
    w(p) += dw+static_noise_w+dynamic_noise_w+w_xterm+w_yterm;
    while (w(p)>360.) {
      w(p) -= 360.;
    }
    while (w(p)<0.) {
      w(p) += 360.;
    }
  }
  mutex.unlock();
  auto time = timer.elapsed();
 // std::cout << "update Motion : " << time << " ms\n";
}

void MCL::updateSensor(const std::vector<MCL::SensorData> &data)
{
  utility::timer timer;
  mutex.lock();
  int n_data = data.size();
  if(n_data<=0)
    return;
  double weight_sum(0.0);
  double weight_sum_cmps(0.0);
  for(auto& p : particles)
  {
    double err_sum(0.0);
    for(auto d : data)
    {
      double c = cos(w(p)*TO_RAD);
      double s = sin(w(p)*TO_RAD);
      double world_x = c*x(d)+s*y(d)+x(p);
      double world_y = -s*x(d)+c*y(d)+y(p);
      double distance = field.distance(world_x,world_y);
      distance = distance*distance;
      double pt_distance = sqrt(x(d)*x(d)+y(d)*y(d));
      err_sum += distance;
    }
    //    double cmps_err = 10.0*fabs(cmps_error(w(p)));
    double p_weight = 1.0/(err_sum/*+cmps_err*/)/n_data;
    vis_weight(p) = p_weight;
    weight_sum += p_weight;
    double cmps_err = 180.0/std::max(fabs(cmps_error(w(p))),1.);
    cmps_weight(p) = cmps_err;
    weight_sum_cmps += cmps_err;
  }
  double w_avg(0.0);
  for(auto& p : particles){
    vis_weight(p) /= weight_sum;
    cmps_weight(p) = (cmps_weight(p)/weight_sum_cmps);
    total_weight(p) = wcmps*cmps_weight(p) + wvision*vis_weight(p);
  }
  w_avg = (weight_sum*wvision+wcmps*weight_sum_cmps)/N_PARTICLE;
  // double w_avg = weight_sum/N_PARTICLE;
  //    std::cout << "W_AVG : " << w_avg << '\n';
  w_slow = w_slow + a_slow*(w_avg-w_slow);
  w_fast = w_fast + a_fast*(w_avg-w_fast);
  //======================
  if(w_slow>1)w_slow=1;
  if(w_fast>10)w_fast=10;
  //======================
  resample();
  mutex.unlock();
  auto time = timer.elapsed();
  //std::cout << "update Measurement : " << time << " ms; "
  //          << "w_slow : " << w_slow << "; w_fast : " << w_fast
  //          << std::endl;
}

void MCL::updateCompass(double compass)
{
  cmps = compass;
}

MCL::State MCL::estimation()
{
  mutex.lock();
  double x_mean = 0.0;
  double y_mean = 0.0;
  double w_mean = 0.0;
//===========================
  Particles temp;
  Float* x_elem = new Float[N_PARTICLE];
  Float* y_elem = new Float[N_PARTICLE];
  double std_x, std_y, std_xy;
  static double x_mean_, y_mean_;
  for(int i=0; i<particles.size(); i++)
  {
    x_elem[i]=x(particles.at(i));
    y_elem[i]=y(particles.at(i));
  }
  fVector x_(N_PARTICLE, x_elem);
  fVector y_(N_PARTICLE, y_elem);
  std_x=Std(x_);
  std_y=Std(y_);
  std_xy = (std_x+std_y)/2;
  sd = std_xy;
  //cout<<std_xy<<endl;

  if(std_xy<80){
    x_mean_=0;
    y_mean_=0;
    for(auto p : particles)
    {
      x_mean_ += (1.0/N_PARTICLE)*x(p);
      y_mean_ += (1.0/N_PARTICLE)*y(p);
    }
  }
  if(std_xy<200){
    //cout<<std_xy<<endl;
    //cout<<temp.size()<<endl;
    for(int i=0; i<particles.size(); i++)
    {
      double distance = sqrt(pow(x(particles.at(i))-x_mean_,2)+pow(y(particles.at(i))-y_mean_,2));
      if(distance<40){
      //cout<<fabs(x(particles.at(i))-x_mean_)<<endl;
      //if(fabs(x(particles.at(i))-x_mean_)<60){
        temp.push_back(particles.at(i));
        //cout<<"erase"<<i<<endl;
      }
    }
    x_mean_=0;
    y_mean_=0;
    for(auto p : temp)
    {
      x_mean_ += (1.0/temp.size())*x(p);
      y_mean_ += (1.0/temp.size())*y(p);
    }
    //cout<<temp.size()<<endl;
  }
//===========================
  for(auto p : temp)
  {
    //cout<<temp.size()<<endl;
    //x_mean += (1.0/N_PARTICLE)*x(p);
    //y_mean += (1.0/N_PARTICLE)*y(p);
    x_mean += (1.0/temp.size())*x(p);
    y_mean += (1.0/temp.size())*y(p);
    double wm_tmp = w_mean;
    while(wm_tmp>360.)
      wm_tmp -= 360.;
    while (wm_tmp<0.)
      wm_tmp += 360.;
    double dw = w(p) - wm_tmp;
    if(dw>180.) {
      dw = -(360. - dw);
    }
    else if(dw<-180.) {
      dw = 360. + dw;
    }
    //w_mean += (1.0/N_PARTICLE)*(720./180.)*dw;
    w_mean += (1.0/temp.size())*(720./180.)*dw;
  }
  while(w_mean>360.)
    w_mean -= 360.;
  while (w_mean<0.)
    w_mean += 360.;
  x(pose_estimation) = x_mean;
  y(pose_estimation) = y_mean;
  w(pose_estimation) = w_mean;
  mutex.unlock();
  return std::make_tuple(x_mean,y_mean,w_mean);
}

MCL::State MCL::weighted_estimation()
{
  mutex.lock();
  double x_mean = x(pose_estimation);
  double y_mean = y(pose_estimation);
  double w_mean = 0.;
//==================
  Particles temp;
  Float* x_elem = new Float[N_PARTICLE];
  Float* y_elem = new Float[N_PARTICLE];
  double std_x, std_y, std_xy;
  double x_mean_, y_mean_;
  for(int i=0; i<particles.size(); i++)
  {
    x_elem[i]=x(particles.at(i));
    y_elem[i]=y(particles.at(i));
  }
  fVector x_(N_PARTICLE, x_elem);
  fVector y_(N_PARTICLE, y_elem);
  std_x=Std(x_);
  std_y=Std(y_);
  std_xy = (std_x+std_y)/2;
 
  //cout<<std_xy<<endl;
  if(std_xy<200){
    for(auto p : particles)
    {
      x_mean_ += (1.0/N_PARTICLE)*x(p);
      y_mean_ += (1.0/N_PARTICLE)*y(p);
    }
    //cout<<temp.size()<<endl;
    for(int i=0; i<particles.size(); i++)
    {
      //if(fabs(x(particles.at(i))-x_mean_)<60&&fabs(y(particles.at(i))-y_mean_)<60){
      //int distance = sqrt(pow(x(particles.at(i))-x_mean_,2)+pow(y(particles.at(i))-y_mean_,2));
      //if(distance<40){
        temp.push_back(particles.at(i));
        //cout<<"erase"<<i<<endl;
        //temp.erase(temp.begin()+i);
      //}
    }
    //cout<<temp.size()<<endl;
  }
//==================
  for(auto p : temp)
  {
    auto pw = total_weight(p);
    x_mean += (pw)*(x(p)-x(pose_estimation));
    y_mean += (pw)*(y(p)-y(pose_estimation));
    double wm_tmp = w_mean;
    while(wm_tmp>360.)
      wm_tmp -= 360.;
    while (wm_tmp<0.)
      wm_tmp += 360.;
    double dw = w(p) - wm_tmp;
    if(dw>180.) {
      dw = -(360. - dw);
    }
    else if(dw<-180.) {
      dw = 360. + dw;
    }
    w_mean += (pw)*(720./180.)*dw;
  }
  while(w_mean>360.)
    w_mean -= 360.;
  while (w_mean<0.)
    w_mean += 360.;
  // x(pose_estimation) = x_mean;
  // y(pose_estimation) = y_mean;
  // w(pose_estimation) = w_mean;
  mutex.unlock();
  return std::make_tuple(x_mean,y_mean,w_mean);
}

void MCL::resetParticles(bool init, double xpos, double ypos, double wpos)
{
  std::random_device xrd, yrd, wrd;
  w_fast=0.0, w_slow=0.0;
  if(init)
  {
    std::normal_distribution<double> xrg(xpos,xvar), yrg(ypos,yvar), wrg(wpos,wvar);
    for(auto& p : particles)
    {
      x(p) = xrg(xrd);
      y(p) = yrg(yrd);
      w(p) = wrg(wrd);
    }
  }
  else
  {
    std::uniform_real_distribution<double> xrg(-300,300), yrg(-200,200), wrg(0,360);
    for(auto& p : particles)
    {
      x(p) = xrg(xrd);
      y(p) = yrg(yrd);
      w(p) = wrg(wrd);
    }
  }
}

void MCL::setRandomParameter(double xv, double yv, double wv)
{
  xvar = xv;
  yvar = yv;
  wvar = wv;
}

inline
void MCL::resample()
{
  Particles plist;
  std::random_device rd;
  std::mt19937 gen(rd());
  std::uniform_real_distribution<> rg(0.0,1.0/N_PARTICLE);
  double r = rg(gen);
  // double c = vis_weight(particles[0]);
  double c = total_weight(particles[0]);
  int idx = 0;
  std::random_device rd1;
  std::mt19937 gen1(rd1());
  std::random_device rd2;
  std::mt19937 gen2(rd2());
  std::uniform_real_distribution<double> xrg(-300,300), yrg(-200,200), wrg(0,360);
  double random_prob = (1.0-(w_fast/w_slow));
  // std::bernoulli_distribution random_gen((random_prob<0) ? 0.0 : (random_prob>1 ? 1.0 : random_prob));
  std::bernoulli_distribution random_gen(std::max(0.0,random_prob));
  for(int i=0; i<N_PARTICLE; i++)
  {
    if(random_gen(gen1))
    {
      plist.push_back(std::make_tuple(xrg(gen2),yrg(gen2),wrg(gen2),wvision/N_PARTICLE,wcmps/N_PARTICLE,1.0/N_PARTICLE));
    }
    else
    {
      double u = r+((double)i/N_PARTICLE);
      while (u>c) {
        idx += 1;
        // c += vis_weight(particles[idx]);
        c += total_weight(particles[idx]);
      }
      plist.push_back(particles[idx]);
    }
  }
  particles = plist;
}

double MCL::cmps_error(double &angle)
{
  while(angle>360.) {
    angle -= 360.;
  }
  while (angle<0.) {
    angle += 360.;
  }
  double err = angle-cmps;
  if(fabs(err)>180.0) {
    err = 360.0-fabs(err);
  }
  return err;
}

MCL::FieldMatrix::FieldMatrix()
{
  xline.push_back(XLINE1);
  xline.push_back(XLINE2);
  xline.push_back(XLINE3);
  xline.push_back(XLINE4);
  xline.push_back(XLINE5);
  xline.push_back(XLINE6);
  xline.push_back(XLINE7);

  yline.push_back(YLINE1);
  yline.push_back(YLINE2);
  yline.push_back(YLINE3);
  yline.push_back(YLINE4);
  yline.push_back(YLINE5);
  yline.push_back(YLINE6);

  start_x = -xline[0]-100;
  end_x = xline[0]+100;
  start_y = -yline[0]-100;
  end_y = yline[0]+100;
  x_length = end_x-start_x+1;
  y_length = end_y-start_y+1;
//=======================
    distance_matrix = (double*) malloc(sizeof(double)*x_length*y_length);
    //#define TEST ros::package::getPath("vision")+"/localization/errortable.bin"
    string vision_path = ros::package::getPath("self_localization");
    string FILE_PATH = "/self_localization/src/errortable.bin";
    string Filename = vision_path + FILE_PATH;
    const char *Filename_Path = Filename.c_str();
    if(ifstream(Filename)){
        // open the file:
        streampos fileSize;
        std::ifstream file(Filename_Path, ios::binary);
        // get its size:
        file.seekg(0, ios::end);
        fileSize = file.tellg();
        file.seekg(0, ios::beg);
        // read the data:
        vector<BYTE> fileData(fileSize);
        file.read((char *)distance_matrix, fileSize);
        cout<<"read bin finish"<<endl;

        cv::Mat distance_map(DISTANCE_MATRIX_HEIGHT, DISTANCE_MATRIX_WIDTH, CV_8UC3, Scalar(255,255,255));
        for(int i=0; i<DISTANCE_MATRIX_WIDTH; i++)
        {
            for(int j=0; j<DISTANCE_MATRIX_HEIGHT; j++)
            {
                auto color = (int)(distance((double)i-DISTANCE_MATRIX_WIDTH/2,(double)j-DISTANCE_MATRIX_HEIGHT/2))+50;
                auto px = (color>255)?    (255)    :    (color<0?0:color);
                px = 255-px;
            }
        }
        //cv::imshow("distance_map",distance_map);
        //cv::waitKey(10);
    }else{
        cout<<"can not find the bin file.\n";
    }
//===========================
}

double MCL::FieldMatrix::distance(double x, double y)
{
  if((abs((int)x)<=end_x) &&
     (abs((int)y)<=end_y))
    return distance_matrix[((int)(y)-start_y)*x_length+(int)(x)-start_x];
  else
  {
    //        std::cout << "[FieldMatrix] index out of bound\n";
    //return 500.0;
    return 300;
  }
}


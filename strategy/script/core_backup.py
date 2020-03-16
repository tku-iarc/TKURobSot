#!/usr/bin/env python
import rospy
import sys
import math
import time
from statemachine import StateMachine, State
from robot.robot import Robot
from std_msgs.msg import String
from my_sys import log, SysCheck, logInOne
from methods.chase import Chase
from methods.attack import Attack
from methods.behavior import Behavior
from methods.defense import Defense
from dynamic_reconfigure.server import Server as DynamicReconfigureServer
from strategy.cfg import RobotConfig
import dynamic_reconfigure.client

class Core(Robot, StateMachine):

  last_ball_dis = 0
  last_goal_dis = 0
  last_time     = time.time()
  
  idle   = State('Idle', initial = True)
  chase  = State('Chase')
  attack = State('Attack')
  defense = State('Defense')
  shoot  = State('Shoot')
  point  = State('Point')
  movement = State('Movement')

  toIdle   = chase.to(idle) | attack.to(idle)  | movement.to(idle) | point.to(idle) | shoot.to(idle) | idle.to.itself() | defense.to(idle)
  toChase  = idle.to(chase) | attack.to(chase) | chase.to.itself() | movement.to(chase) | point.to(chase) | defense.to(chase)
  toAttack = attack.to.itself() | shoot.to(attack) | movement.to(attack)| chase.to(attack)| point.to(attack) | defense.to(attack)
  toDefense = idle.to(defense) | defense.to.itself() | chase.to(defense)
  toShoot  = attack.to(shoot)| idle.to(shoot)|movement.to(shoot) | defense.to(shoot)
  toMovement = chase.to(movement) | movement.to.itself()| idle.to(movement) | point.to(movement)  | defense.to(movement)
  toPoint  = point.to.itself() | idle.to(point) | movement.to(point) | chase.to(point) | defense.to(point)
  #==================
  back_ang = 10
  back_dis = 60
  #==================
  def Callback(self, config, level):
    self.game_start = config['game_start']
    self.game_state = config['game_state']
    self.chase_straight = config['chase_straight']
    self.run_point  = config['run_point']
    self.our_side   = config['our_side']
    self.opp_side   = 'Blue' if self.our_side == 'Yellow' else 'Yellow'
    self.run_x      = config['run_x']
    self.run_y      = config['run_y']
    self.run_yaw    = config['run_yaw']
    self.strategy_mode = config['strategy_mode']
    self.attack_mode = config['attack_mode']
    self.maximum_v = config['maximum_v']
    self.orb_attack_ang = config['orb_attack_ang']
    self.atk_shoot_ang = config['atk_shoot_ang']
    self.shooting_start = config['shooting_start']
    self.Change_Plan = config['Change_Plan']
    self.atk_shoot_dis = config['atk_shoot_dis']
    self.my_role       = config['role']
    self.accelerate = config['Accelerate']
    self.ball_speed = config['ball_pwm']

    self.ChangeVelocityRange(config['minimum_v'], config['maximum_v'])
    self.ChangeAngularVelocityRange(config['minimum_w'], config['maximum_w'])
    self.ChangeBallhandleCondition(config['ballhandle_dis'], config['ballhandle_ang'])

    self.SetMyRole(self.my_role)
    
    return config

  def __init__(self, sim = False):
    super(Core, self).__init__(sim)
    StateMachine.__init__(self)
    self.CC  = Chase()
    self.AC  = Attack()
    self.BC  = Behavior()
    self.DC  = Defense()
    self.left_ang = 0
    self.dest_angle = 0
    
    dsrv = DynamicReconfigureServer(RobotConfig, self.Callback)

  def on_toIdle(self):
    self.goal_dis = 0
    for i in range(0, 10):
        self.MotionCtrl(0,0,0)
    log("To Idle1")

  def on_toChase(self, method = "Classic"):
    t = self.GetObjectInfo()
    side = self.opp_side
    our_side = self.our_side
    opp_info = self.GetOppInfo()
    opphandle = self.GetOppHandle()
    robot_info = self.GetRobotInfo()
    # print(opphandle, opp_info['ang'])
    x=0
    y=0
    yaw=0
    if(opphandle==True and opp_info['ang']!=999):
      method = "Block"
    if(method =="Block"):
      #print("block")
      dis = 0
      ang = 0
      #========more catch ball====
      if(t['ball']['ang']<999):
        dis = t['ball']['dis']
        ang = t['ball']['ang']
      else:
        dis = opp_info['dis']
        ang = opp_info['ang']
      #========more defense=======
      # dis = opp_info['dis']
      # ang = opp_info['ang']
      x, y, yaw = self.CC.ClassicRounding(t[side]['ang'],\
                                          dis,\
                                          ang)
      if(our_side=="Yellow"):
        yaw = 0
      elif(our_side=="Blue"):
        yaw = 180

      v_yaw = yaw - robot_info['location']['yaw']
      if abs(v_yaw - 360) < abs(v_yaw):
        yaw = v_yaw - 360
      elif abs(v_yaw + 360) < abs(v_yaw):
        yaw = v_yaw + 360
      else:
        yaw = v_yaw
      #======full speed block====
      if(dis<60 and abs(ang)>10):
        y=y*10
      if(x<0):
        x=x*10
      #==========================
    if method == "Classic":
      x, y, yaw = self.CC.ClassicRounding(t[side]['ang'],\
                                          t['ball']['dis'],\
                                          t['ball']['ang'])
      if self.ball_speed:
        x, y, yaw = self.CC.ClassicRounding2(t[side]['ang'],\
                                             t['ball']['dis'],\
                                             t['ball']['ang'],\
                                             t['ball']['speed_pwm_x'],\
                                             t['ball']['speed_pwm_y'])
    elif method == "Straight":
      x, y, yaw = self.CC.StraightForward(t['ball']['dis'], t['ball']['ang'])

    # elif method == "Defense":
    #   x, y, yaw = self.AC.Defense(t['ball']['dis'], t['ball']['ang'])
    if self.accelerate:
      self.Accelerator(80)
    if self.ball_speed:
      x = x + t['ball']['speed_pwm_x']
      y = y + t['ball']['speed_pwm_y']

    self.MotionCtrl(x, y, yaw)

  def on_toAttack(self, method = "Classic"):
    t = self.GetObjectInfo()
    side = self.opp_side
    l = self.GetObstacleInfo()      
    if method == "Classic":
      #x, y, yaw = self.AC.ClassicAttacking(t[side]['dis'], t[side]['ang'])
      x, y, yaw = self.AC.Escape(t[side]['dis'],\
                                 t[side]['ang'])
    elif method == "Cut":
      x, y, yaw = self.AC.Cut(t[side]['dis'], t[side]['ang'],self.run_yaw)
    elif method == "Post_up":
      if t[side]['dis'] < 50 :
        t[side]['dis'] = 50
      # x, y, yaw = self.AC.Post_up(t[side]['dis'],\
      #                                  t[side]['ang'],\
      #                                  l['ranges'],\
      #                                  l['angle']['increment'])
      x, y, yaw = self.AC.Post_up2(t[side]['dis'],\
                                   t[side]['ang'])
    elif method == "Orbit":
      x, y, yaw, arrived = self.BC.Orbit(t[side]['ang'])
      if(arrived):
        x, y, yaw = self.AC.Escape(t[side]['dis'],\
                                   t[side]['ang'])
      self.MotionCtrl(x, y, yaw, True)
       
    self.MotionCtrl(x, y, yaw)

  def on_toShoot(self, power, pos = 1):
    self.RobotShoot(power, pos)
  def on_toDefense(self):
    #print("defense")
    t = self.GetObjectInfo()
    robot = self.GetRobotInfo()
    our_side = self.our_side
    opp_side = self.opp_side
    obstacles_info = self.GetObstacleInfo()
    obs = obstacles_info["detect_obstacles"]

      
    if(t['ball']['ang']==999):
      
      block_flag, obs_dis, obs_ang = self.DC.BlockCheck(t[our_side]['dis'],\
                                                        t[our_side]['ang'],\
                                                        our_side)
      #========block opp robot=====
      if(block_flag):
        #print(block_flag)
        x, y, yaw = self.CC.ClassicRounding(t[opp_side]['ang'],\
                                            obs_dis,\
                                            obs_ang)
        v_yaw = 90 - robot['location']['yaw']
        if abs(v_yaw - 360) < abs(v_yaw):
          yaw = v_yaw - 360
        elif abs(v_yaw + 360) < abs(v_yaw):
          yaw = v_yaw + 360
        else:
          yaw = v_yaw
        #print(x, y, yaw, obs_dis, obs_ang)
        self.MotionCtrl(x, y, yaw)                              
      else:
        #========back to defense====
        p_x, p_y, p_yaw = self.DC.ClassicDefense(t[our_side]['dis'],\
                                                 t[our_side]['ang'],\
                                                 our_side)
        x, y, yaw, arrived = self.BC.Go2Point(p_x, p_y, p_yaw)
        if(math.sqrt(math.pow((robot['location']['x']-p_x),2) + math.pow((robot['location']['y']-p_y),2) ) <20 and abs(robot['location']['yaw']-p_yaw)<20):
          x=0
          y=0
          yaw = 0
        if(math.sqrt(math.pow((robot['location']['x']-p_x),2) + math.pow((robot['location']['y']-p_y),2) ) < 60): 
          self.MotionCtrl(x, y, yaw, False, 10)
        else:
          self.MotionCtrl(x, y, yaw)
      #===========================


  def on_toMovement(self, method):
    t = self.GetObjectInfo() 
    position = self.GetRobotInfo()
    side = self.opp_side
    ourside = self.our_side
    l = self.GetObstacleInfo()
    #log('move')
    if method == "Orbit":
      x, y, yaw, arrived = self.BC.Orbit(t[side]['ang'])
      self.MotionCtrl(x, y, yaw, True)

    elif method == "Relative_ball":
       
      x, y, yaw = self.BC.relative_ball(t[ourside]['dis'],\
                                        t[ourside]['ang'],\
                                        t['ball']['dis'],\
                                        t['ball']['ang'])
      self.MotionCtrl(x, y, yaw)
    elif method == "Relative_goal":
      x, y, yaw = self.BC.relative_goal(t[ourside]['dis'],\
                                             t[ourside]['ang'],\
                                             t['ball']['dis'],\
                                             t['ball']['ang'])
      self.MotionCtrl(x, y, yaw)

    elif method == "Penalty_Kick":
      x, y, yaw = self.BC.PenaltyTurning(side, self.run_yaw, self.dest_angle)
      self.left_ang = abs(yaw)
      self.MotionCtrl(x, y, yaw )
      
    elif method == "At_Post_up":
      # x, y, yaw = self.BC.Post_up(t[side]['dis'],\
      #                                  t[side]['ang'],\
      #                                  l['ranges'],\
      #                                  l['angle']['increment'])
      x, y, yaw = self.BC.Steal(t[ourside]['dis'],\
                                t[ourside]['ang'],\
                                Core.back_dis,\
                                Core.back_ang)
      self.MotionCtrl(x, y, yaw)

  def on_toPoint(self):
    t = self.GetObjectInfo()
    our_side = self.our_side
    opp_side = self.opp_side
    if self.run_yaw == 0:
      yaw = t[our_side]['ang']
    elif self.run_yaw == 180:
      yaw = t[opp_side]['ang']
    elif self.run_yaw == -180:
      yaw = t['ball']['ang']
    else :
      yaw = self.run_yaw
    x, y, yaw, arrived = self.BC.Go2Point(self.run_x, self.run_y, yaw)

    self.MotionCtrl(x, y, yaw)
    return arrived

  def PubCurrentState(self):
    self.RobotStatePub(self.current_state.identifier)

  def CheckBallHandle(self):
    if self.RobotBallHandle():
      ## Back to normal from Accelerator
      self.ChangeVelocityRange(0, self.maximum_v)
      Core.last_ball_dis = 0

    return self.RobotBallHandle()

  def Accelerator(self, exceed = 100):
    t = self.GetObjectInfo()
    if Core.last_ball_dis == 0:
      Core.last_time = time.time()
      Core.last_ball_dis = t['ball']['dis']
    elif t['ball']['dis'] >= Core.last_ball_dis:
      if time.time() - Core.last_time >= 0.8:
        self.ChangeVelocityRange(0, exceed)
    else:
      Core.last_time = time.time()
      Core.last_ball_dis = t['ball']['dis']

  def change_plan(self):
    t = self.GetObjectInfo()
    opp_side = self.opp_side 
    if Core.last_goal_dis == 0:
      Core.last_time = time.time()
      Core.last_goal_dis = t[opp_side]['dis']
    elif t[opp_side]['dis'] >= Core.last_goal_dis:
      if time.time() - Core.last_time >= 3:
        return True
    else:
      Core.last_time = time.time()
      Core.last_goal_dis = t[opp_side]['dis']
      return False
  def record_angle(self):
    position = self.GetRobotInfo()
    self.dest_angle = math.degrees(position['imu_3d']['yaw']) - self.run_yaw

class Strategy(object):
  def __init__(self, sim=False):
    rospy.init_node('core', anonymous=True)
    self.rate = rospy.Rate(200)
    self.robot = Core(sim)
    self.dclient = dynamic_reconfigure.client.Client("core", timeout=30, config_callback=None)
    self.main()

  def RunStatePoint(self):
    print("run point")
    if self.robot.run_point == "ball_hand":
      if self.robot.toPoint():
        self.dclient.update_configuration({"run_point": "none"})
        self.ToMovement()
    elif self.robot.run_point == "empty_hand":
      if self.robot.toPoint():
        self.dclient.update_configuration({"run_point": "none"})
        self.ToChase()

  def ToChase(self):
    mode = self.robot.attack_mode
    if mode == "Defense":
      self.ToMovement()

    else:
      if not self.robot.chase_straight :
        self.robot.toChase("Classic")
      else:
        self.robot.toChase("Straight")

  def ToAttack(self):
    mode = self.robot.attack_mode
    if mode == "Attack" :
      self.robot.toAttack("Classic")
    elif mode == "Cut":
      self.robot.toAttack("Cut")
    elif mode == "Post_up":
      self.robot.toAttack("Post_up")
    elif mode == "Orbit":
      self.robot.toAttack("Orbit")

  def ToMovement(self):
    mode = self.robot.strategy_mode
    state = self.robot.game_state
    point = self.robot.run_point
    #log(point)
    if point == "ball_hand":
      self.RunStatePoint()
    elif state == "Penalty_Kick":
      self.robot.toMovement("Penalty_Kick")
    elif mode == "At_Post_up":
      #log("movement")
      self.robot.toMovement("At_Post_up")
    elif mode == "At_Orbit":
      self.robot.toMovement("Orbit")
    elif mode == "Defense_ball":
      self.robot.toMovement("Relative_ball")
    elif mode == "Defense_goal":
      self.robot.toMovement("Relative_goal")
    elif mode == "Fast_break":
      self.ToAttack()

  
  def main(self):
    while not rospy.is_shutdown():
      self.robot.PubCurrentState()
      self.robot.Supervisor()

      targets = self.robot.GetObjectInfo()
      position = self.robot.GetRobotInfo()
      mode = self.robot.strategy_mode
      state = self.robot.game_state
      laser = self.robot.GetObstacleInfo()
      point = self.robot.run_point

      # Can not find ball when starting
      if targets is None or targets['ball']['ang'] == 999 and self.robot.game_start:
        print("Can not find ball")

        #self.robot.toIdle()
        self.robot.toDefense()
      else:
        if self.robot.is_defense:
          self.robot.toIdle()
        if not self.robot.is_idle and not self.robot.game_start:
          self.robot.toIdle()
        if self.robot.is_idle:          
          if self.robot.game_start:
            if self.robot.shooting_start:
              if self.robot.CheckBallHandle():
                self.robot.RobotShoot(80, 1)
              else:
                x = time.time()
                while 1:                
                  self.robot.MotionCtrl(30, 0, 0)
                  if (time.time() - x ) > 1: break
              self.dclient.update_configuration({"shooting_start": False})
            elif state == "Penalty_Kick":
              self.robot.record_angle()
              self.ToMovement()
            elif self.robot.run_point == "empty_hand":
              self.RunStatePoint()
            else :
              print('idle to chase')
              self.ToChase()

        if self.robot.is_chase:
          #log(self.robot.dest_angle)
          if self.robot.CheckBallHandle():
            print('chase to move')
            self.ToMovement()
          else:
            self.ToChase()
        if self.robot.is_movement:          
          if state == "Penalty_Kick":
            if self.robot.left_ang <= self.robot.atk_shoot_ang:
              log("stop") 
              self.robot.toShoot(100)
              self.dclient.update_configuration({"game_state": "Kick_Off"})
            else:
              self.ToMovement()         
          elif mode == 'At_Orbit':
            if abs(targets[self.robot.opp_side]['ang']) < self.robot.orb_attack_ang:
              self.ToAttack()
            elif not self.robot.CheckBallHandle():
              self.ToChase()
            else:
              self.ToMovement()

          elif mode == 'At_Post_up':
            # if targets[self.robot.opp_side]['dis'] <= self.robot.atk_shoot_dis:
            #   self.ToAttack()
            # elif not self.robot.CheckBallHandle():
            #     self.ToChase()
            # else:
            #   self.ToMovement() 
            post_up_checked = False
           
            obs = laser["detect_obstacles"]
            for j in range (0, len(obs), 4):
              dis = obs[j+0]
              ang = obs[j+1]
              if(abs(ang) < Core.back_ang and dis < Core.back_dis):
                post_up_checked = True
                break
            if targets[self.robot.our_side]['dis']<100:
              post_up_checked = False
            
            if not self.robot.CheckBallHandle():
              self.ToChase()
            elif not post_up_checked:
              #print("attack")
              self.ToAttack()
            else:
              #print("back")
              self.ToMovement()             

          elif mode == "Defense_ball" or mode == "Defense_goal":  
            if self.robot.CheckBallHandle():
              self.dclient.update_configuration({"strategy_mode": "Fast_break"})
              self.dclient.update_configuration({"attack_mode": "Attack"})

              self.ToChase()
            else : 
              self.ToMovement()

          elif mode == "Fast_break":
            self.ToAttack()

        if self.robot.is_attack:
         
          if not self.robot.CheckBallHandle():
            self.robot.last_goal_dis = 0
            self.ToChase()
          elif  abs(targets[self.robot.opp_side]['ang']) < self.robot.atk_shoot_ang and \
                abs(targets[self.robot.opp_side]['dis']) < self.robot.atk_shoot_dis:
            self.robot.toShoot(100)
          else:
            self.ToAttack()

        if self.robot.is_shoot:
          self.ToAttack()

        ## Run point
        if self.robot.is_point:
          if point == "ball_hand":
            if self.robot.CheckBallHandle():
              self.RunStatePoint()
            else:
              self.ToChase()
          else:
            self.RunStatePoint()


        if rospy.is_shutdown():
          log('shutdown')
          break

        self.rate.sleep()

if __name__ == '__main__':
  try:
    if SysCheck(sys.argv[1:]) == "Native Mode":
      log("Start Native")
      s = Strategy(False)
    elif SysCheck(sys.argv[1:]) == "Simulative Mode":
      log("Start Sim")  
      s = Strategy(True)
  except rospy.ROSInterruptException:
    pass 

#
# Python Lineart Plotter
#
# Working with Adafruit's pi-stepper
# kit.
#
# recommended initial usage with repl ie:
# "python3 -i plotter.py"
# Then at the repl.
# >>> pl.plot_calibrate()
#
# You need to set up the geometry correctly
# in the code for plotter::initialize() for your setup.
# then you can print files.
#
# The plotter uses simple files of
# pickled lists to draw. (mono or CYMK)
# file = path or [c_path, y_path ...  ]
# path = [lines]
# lines = [vertices] (ie: [[1.,1.],[1.,2.]])
# pickle the path list, put in the working directory.
# and call "pl=plotter()" that's it.
#
# These lists can be made from jpg by some of the
# 'lineifiers' in the lineifiers file.
# although those operations are a matter of art
# and best done on a desktop as they are
# often prohibitively expensive for raspberry pi's.
# as implemented here. The path planning is better off
# on the desktop too.
#
# Very little is adafruit specific or hard-coded
# besides the fact that I use the 15th PWM channel
# to drive the lifter servo(s), and that the PWM
# controller is found at I2C addr 0x60
# (i2cdetect -y 1)
# also stepper1 is left and stepper2 is right.
# the images directory documents some of the hardware build.
#
# ---------------------------------------
# Wholly authored by John Parkhill (2019)
# while on planes and shit (john.parkhill@gmail.com).
# John Parkhill retains copyright.
# John Parkhill is not liable for any consequences stemming
# from the use of this software and no gurantees are implied.
# ---------------------------------------
#
# Distributed under Creative Commons Share-alike license.
#
from math import sqrt, pow, cos, sin, pi, atan
import copy, pickle, os, time
import numpy as np
HAS_ADAF = True
try:
    from plotter_kit import *
    # from adafruit_motorkit import MotorKit as MK
    # from adafruit_servokit import ServoKit as SK
except Exception as Ex:
    HAS_ADAF = True
    # print(Ex)
    # pass
    print("No Adafruit modules found.")
    print(Ex)
    print("I'm a mock plotter now.")
    HAS_ADAF = False
    # Also mock time.
    class timeclass:
        def __init__(self):
            self.TIMER = 0
        def time(self):
            return self.TIMER
        def sleep(self,X):
            self.TIMER += X
        def hours(self):
            return self.TIMER/(3600.)
    time = timeclass()
def sign(X):
    if X>0:
        return 1
    elif(X<0):
        return -1
    elif (X == 0):
        return 0
def ngon(X=0, Y=0, r=1, n=6, phase = 0):
    pts = []
    step = 2*pi/n
    for K in range(n):
        pts.append([X + r*cos(K*step+phase),
                    Y+r*sin(K*step+phase)])
    return pts
def depth(l):
    if isinstance(l, list):
        if (len(l)==0):
            return 1
        return 1 + max(depth(item) for item in l)
    else:
        return 0
class Interpolation:
    def __init__(self, xmax, ymax, npts=6, pad=10.):
        """
        For caternary correction.
        Call 'plot_raw_grid' then measure your real grid.
        either enter the points by set() or hard-code them.
        inverse maps to what the motors should drive to by
        using averages of neighbors.
        """
        self.Xs = np.linspace(pad, xmax-pad, npts)
        self.Ys = np.linspace(pad, ymax-pad, npts)
        self.Pts = np.stack(np.meshgrid(self.Xs,self.Ys),0).reshape(2,npts*npts).T
        self.Zs = self.Pts.copy()
    def set(self, new_points):
        self.Zs = np.array(new_points)
    def __call__(self,X,Y):
        """
        Map XY in pts onto Zs
        """
        D = np.power((self.Pts - np.array([X,Y])), 2.0).sum(-1)
        w = np.exp(-np.clip(D,0,30.0))
        n = w.sum()
        w /= n
        return (self.Zs*(w[:,np.newaxis])).sum(0).tolist()
class JStepper:
    def __init__(self, ada_stepper,
                step_delay = 0.05,
                style = 'INTERLEAVE'):
        self.step = ada_stepper
        self.mock = ada_stepper is None
        self.step_delay = step_delay
        if (not self.mock):
            self.CWd = FORWARD
            self.CCWd = BACKWARD
            if (style == 'SINGLE'):
                self.step_type = SINGLE
                self.steps_per_rev = 200
            if (style == 'DOUBLE'):
                self.step_type = DOUBLE
                self.steps_per_rev = 200
            elif (style == 'INTERLEAVE'):
                self.step_type = INTERLEAVE
                self.steps_per_rev = 400
        else:
            self.CWd = None
            self.CCWd = None
            self.steps_per_rev = 400
            self.step_type = None
        self.odo = 0
        self.step_pos = 0
        self.log = []
        return
    def release(self):
        if (not self.step is None):
            self.step.release()
    @property
    def angle(self):
        return 360.0*self.step_pos/self.steps_per_rev
    def CW(self,n=1):
        for k in range(n):
            self.odo += 1
            self.step_pos = self.odo % self.steps_per_rev
            if (not self.mock):
                self.step.onestep(direction=self.CWd,
                                    style=self.step_type)
                time.sleep(self.step_delay)
            else:
                time.sleep(self.step_delay)
                self.log.append([time.time(), self.odo])
    def CCW(self,n=1):
        for k in range(n):
            self.odo -= 1
            self.step_pos = self.odo % self.steps_per_rev
            if (not self.mock):
                self.step.onestep(direction=self.CCWd,
                                   style=self.step_type)
                time.sleep(self.step_delay)
            else:
                time.sleep(self.step_delay)
                self.log.append([time.time(), self.odo])
        return
class Lifter:
    def __init__(self, a_servo):
        self.servo = a_servo
        self.mock = a_servo is None
        self.state = 0 # 0=down, 1=up
        self.step_delay = 0.3
        if (not self.mock):
            self.servo.actuation_range = 160
            self.servo.angle = 60
        self.log = []
        return
    def up(self):
        if not self.mock:
            self.servo.angle = 160
            time.sleep(self.step_delay)
        else:
            time.sleep(self.step_delay)
            self.log.append([time.time(), 60.])
        self.state = 1
        return
    def down(self):
        if not self.mock:
            self.servo.angle = 60
            time.sleep(self.step_delay)
        else:
            time.sleep(self.step_delay)
            self.log.append([time.time(), 0.])
        self.state = 0
        return
class Plotter:
    def __init__(self, test=False, repl=False, debug=0, vskip=1):
        """
        All units are cm, degrees, seconds, grams
        The top of the left cog is 0,0.
        the top of the right cog is (cog_distance,0)

        The plotter adjusts lengths of left and right strings
        to achieve desired x,y. Resolution is limited
        by the cog diameters (conversely speed).

        The gondola should be roughly half the mass of the
        dangling masses. With motors off the natural
        neutral position of the plotter along the center
        line should be found by releasing the mass.
        """
        self.log = []
        self.debug = debug
        self.vskip = vskip
        self.initialize()
        print("Y0:",self.y0)
        print("Cog Dist {} Bottom {}".format(self.cog_distance, self.bottom_edge))
        print("Print area: X", self.x_lim," Y:", self.y_lim)
        # self.caternary = Interpolation(self.cog_distance, self.bottom_edge)
        print("Step Lengt: ", self.step_dl)
        print("Min Resolu: ", (self.x_lim[1]-self.x_lim[0])//self.step_dl," X ",
                           (self.y_lim[1]-self.y_lim[0])//self.step_dl)
        # if (repl):
        #     return
        print("(r)epl or (c)hoose file. ")
        C = input()
        if (C.lower()=='r'):
            return
        self.choose_file()
        return
    def initialize(self, cog_distance = 80.5,
                    bottom_edge = 48.0,
                    steps_per_rev=400, cog_circum=1.5*2*pi,
                    y0 = 13., x_pad = 18., y_pad = 10.
                  ):
        """
        y0 is a neutral position where the
        gondola sits without stepper force.
        """
        self.bottom_edge = bottom_edge
        self.cog_distance = cog_distance
        self.cog_circum = cog_circum
        self.chain_density = 0.5 # g/cm
        self.plumb_mass = 100 # g
        self.bottom_edge = bottom_edge
        self.stepsum_L=0 # these are KEY. They give the abs. positioning
        self.stepsum_R=0
        # Pen start position
        self.x0 = cog_distance/2.
        self.y0 = y0
        self.x_lim = (x_pad, self.cog_distance - x_pad)
        self.y_lim = (y_pad, self.bottom_edge - y_pad)
        # 1/100th of the plottable length. Just a useful unit.
        self.cent = min(self.x_lim[1]-self.x_lim[0],
                        self.y_lim[1]-self.y_lim[0])/100.
        self.L0, self.R0 = self.xy_to_LR(self.x0,self.y0)
        print("Initializing I2C... ")
        if (HAS_ADAF):
            self.PK = PlotterKit()
            self.s1 = JStepper(self.PK.stepper1)
            self.s2 = JStepper(self.PK.stepper2)
            self.steps_per_rev = self.s1.steps_per_rev
            self.lifter = Lifter(self.PK.servo)
        else:
            self.s1 = JStepper(None)
            self.s2 = JStepper(None)
            self.lifter = Lifter(None)
            self.debug=1
            self.steps_per_rev = 400
        self.step_dl = self.cog_circum/self.steps_per_rev
        self.motor_check()
        self.init_pen(draw=True)
        return
    def motor_check(self):
        self.lifter.up()
        self.s1.CW()
        self.s1.CCW()
        self.s2.CW()
        self.s2.CCW()
        self.lifter.down()
        self.lifter.up()
    def init_pen(self, draw = False):
        print("Initializing pen...")
        self.pen_up()
        self.s1.release()
        self.s2.release()
        print("Move pen near neutral and press ENTER.")
        _ = input()
        self.motor_check()
        print("Tighten it up and press ENTER.")
        _ = input()
        self.stepsum_L=0 # these are KEY. They give the abs. positioning
        self.stepsum_R=0
        if (draw):
            self.draw_circle(self.x0, self.y0, r=0.5)
        return
    #####################################
    # Basic motion control and geometry
    #####################################
    def xy_to_LR(self,x,y):
        """
        The desired L,R lengths for an
        xy coordinate.
        """
        return sqrt(x*x+y*y), sqrt(pow(self.cog_distance-x,2.0)+y*y)
    def LR_to_xy(self,L,R):
        D = self.cog_distance
        x = (L**2 - R**2 + D**2)/(2*D)
        if (L**2 - x**2)<0:
            print("Warning Bad coords L:{} R:{},x:{}".format(L,R,x))
        y = sqrt(abs(L**2 - x**2))
        return x,y
    @property
    def center(self):
        return (self.x_lim[1]+self.x_lim[0])/2.,(self.y_lim[1]+self.y_lim[0])/2.
    @property
    def XY(self):
        return self.xy_now()
    @property
    def LR(self):
        return self.LL, self.RR
    @property
    def AL(self):
        """
        Angle between chain and cog vector
        at left cog.
        """
        X,Y = self.XY
        return atan(Y/X)
    @property
    def AR(self):
        """
        Angle between chain and cog vector
        at right cog.
        """
        X,Y = self.XY
        return atan(Y/(self.cog_distance - X))
    @property
    def chain_tension(self):
        """
        Because the cogs only deliver vertical force at
        an angle this diverges as y=>0 although the cogs
        should slip before then. This helps to establish
        y-Bounds
        """
        return
    def xy_now(self):
        return self.LR_to_xy(self.LL, self.RR)
    def move_x(self,d=1):
        X,Y = self.XY
        self.move_to(X+d,Y)
    def move_y(self,d=1):
        X,Y = self.XY
        self.move_to(X,Y+d)
    def move_to(self, x, y, raw=False):
        """
        Applies caternary correction
        then linearly interpolates in polar space
        by calculating required step differential
        and then interleaving the R steps as evenly
        as possible in the L.
        -----------------------------------------
        THIS IS THE ONLY way to move the plotter,
        no routine should call step_L or step_R
        """
        if (not raw):
            if (x < self.x_lim[0]):
                print("oob X", x, y)
                x = self.x_lim[0]
            if (x > self.x_lim[1]):
                print("oob X", x, y)
                x = self.x_lim[1]
            if (y < self.y_lim[0]):
                print("oob Y", x, y)
                y = self.y_lim[0]
            if (y > self.y_lim[1]):
                print("oob Y", x, y)
                y = self.y_lim[1]
            # x,y = self.caternary(x,y)
        Lp, Rp = self.xy_to_LR(x,y)
        dL = Lp - self.LL
        dR = Rp - self.RR
        nL = round(abs(dL)/self.step_dl)
        nR = round(abs(dR)/self.step_dl)
        if (nL == 0 and nR == 0):
            return
        sL = sign(dL)
        sR = sign(dR)
        slope = abs(dL)/abs(dR)
        NL = 0
        NR = 0
        while NR < nR:
            self.step_R(sR)
            NR += 1
            n_sub_L = int(NR*slope - NL)
            for k in range(n_sub_L):
                if (NL < nL):
                    self.step_L(sL)
                    NL += 1
        while NL < nL:
            self.step_L(sL)
            NL += 1
        self.log_xy()
        return
    @property
    def LL(self):
        return self.L0+self.stepsum_L*self.step_dl
    @property
    def RR(self):
        return self.R0+self.stepsum_R*self.step_dl
    def step_L(self, sign):
        """
        Sign >= => the line grows.
        """
        if sign>0:
            self.s1.CW()
        elif sign<0:
            self.s1.CCW()
        else:
            return
        self.stepsum_L += sign
        if (self.debug>1):
            X,Y = self.XY
            print("L sign:{:d} Lss:{:d} LL:{:0.1f}, X:{:.1f},Y:{:.1f}".format(
                      sign, self.stepsum_L, self.LL, X, Y))
        return
    def step_R(self, sign):
        if sign>0:
            self.s2.CCW()
        elif sign<0:
            self.s2.CW()
        else:
            return
        self.stepsum_R += sign
        if (self.debug>1):
            X,Y = self.XY
            print("R sign:{:d} Rss:{:d} RR:{:0.1f}, X:{:0.1f},Y:{:0.1f}".format(
                      sign, self.stepsum_R, self.RR, X, Y))
        return
    def pen_up(self):
        self.lifter.up()
        return
    def pen_down(self):
        self.lifter.down()
        return
    def log_xy(self):
        if (HAS_ADAF):
            return
        X,Y = self.xy_now()
        self.log.append([time.time(), X, Y])
    def draw_vertices(self, vertices_, cycle=False):
        vertices = vertices_[::self.vskip]
        print("Drawing ", len(vertices), " vertices ")
        t0 = time.time()
        if (len(vertices)<2):
            return
        self.pen_up()
        self.move_to(*vertices[0])
        self.pen_down()
        for K,v in enumerate(vertices):
            if (K%1000==0):
                print(K,"/",len(vertices)," X{:.2f} Y{:.2f} ".format(*self.XY),
                                    "L{:.1f} R{:.1f}".format(*self.LR))
                print("L {:0.1f} (o)".format(self.s1.angle), self.s1.odo, self.stepsum_L)
                print("R {:0.1f} (o)".format(self.s2.angle), self.s2.odo, self.stepsum_R)
            self.move_to(*v)
        if (cycle):
            self.move_to(*vertices[0])
        self.pen_up()
        print("took ", time.time()-t0, "s")
        return
    def draw_paths(self, paths):
        self.init_pen()
        for K,path in enumerate(paths):
            try:
                print(K, "/", len(paths))
                self.draw_vertices(path)
            except KeyboardInterrupt:
                print("(C)ontinue (P)ause (Q)uit these vertices:?")
                inp = input()
                if (inp.lower().count('c')>0):
                    continue
                if (inp.lower().count('p')>0):
                    self.s1.release()
                    self.s2.release()
                    print("paused")
                    _ = input()
                    self.init_pen()
                    continue
                if (inp.lower().count('q')>0):
                    self.pen_up()
                    self.s1.release()
                    self.s2.release()
                    return
        return
    ###################
    # Path planning, scaling, etc.
    ###################
    def sched_paths(self, paths, n_fog = 1000):
        """
        Greedily plans paths to minimize time.
        sorts by X to begin with. Looks at
        the next n_fog
        """
        if (len(paths)<=0):
            return
        if (len(paths)<2):
            return paths
        paths_scheduled = [0]
        paths_remaining = [X for X in range(1,len(paths)) if len(paths[X])>1]
        print("Planning ", len(paths_remaining), " paths.")
        endpt = lambda X: paths[X][-1]
        def endpt_dist(x,y,K):
            ep = endpt(K)
            return sqrt(pow(ep[0]-x, 2.0)+pow(ep[1]-y,2.0))
        while (len(paths_remaining)>1):
            X = endpt(paths_scheduled[-1])
            distances = []
            for K in paths_remaining[:1000]:
                distances.append(endpt_dist(X[0], X[1], K))
            min_di = distances.index(min(distances))
            min_k = paths_remaining[min_di]
            paths_scheduled.append(min_k)
            paths_remaining.remove(min_k)
        if (len(paths_remaining)>0):
            paths_scheduled.append(paths_remaining.pop())
        tore = []
        for K,sched in enumerate(paths_scheduled):
            tore.append(copy.copy(paths[sched]))
        return tore
    def path_bounds(self,path):
        A = np.array(path)
        if (len(A.shape) != 2):
            print(A.shape)
            raise Exception("Bad Path")
        if (A.shape[1]!=2):
            print(A.shape)
            raise Exception("Bad Path")
        return A.min(0).tolist()+A.max(0).tolist()
    def paths_bounds(self, paths):
        if (not type(paths)==list):
            X,Y = self.center
            return [X,Y,X,Y]
        L = [self.path_bounds(X) for X in paths if len(X)>=2]
        if (len(L)==0):
            X,Y = self.center
            return [X,Y,X,Y]
        A = np.array(L)
        return A[:,:2].min(0).tolist()+A[:,2:].max(0).tolist()
    def cymk_bounds(self,cymk):
        A=np.array([self.paths_bounds(cymk[0]),
        self.paths_bounds(cymk[1]),
        self.paths_bounds(cymk[2]),
        self.paths_bounds(cymk[3])])
        return A[:,:2].min(0).tolist()+A[:,2:].max(0).tolist()
    def aspect(self,cbds):
        x_dim = cbds[2]-cbds[0]
        y_dim = cbds[3]-cbds[1]
        ar_paths = x_dim/y_dim
        return ar_paths
    def rotate_paths(self,paths):
        tore = []
        for path in paths:
            npath = []
            for vertex in path:
                npath.append([-1*vertex[1],vertex[0]])
            tore.append(npath)
        return tore
    def auto_rotate(self, paths, cbds):
        AR = self.aspect(cbds)
        if AR<1:
            print("Auto-Rotating.... !!!!!-----")
            return self.rotate_paths(paths)
        return paths
    def scale_paths(self, paths, cbds, reduction = 1.0):
        """
        Fit a line drawing into the plot area. while
        preserving aspect ratio.
        Also moves image to bottom of plot area
        (for best results. )
        """
        x_dim = cbds[2]-cbds[0]
        y_dim = cbds[3]-cbds[1]
        c_paths = [(cbds[2]+cbds[0])/2., (cbds[3]+cbds[1])/2.]
        ar_paths = x_dim/y_dim
        ar_self = (self.x_lim[1]-self.x_lim[0])/(self.y_lim[1]-self.y_lim[0])
        if ar_paths < ar_self:
            # y is the limiting.
            scale_fac = abs(.99*(self.y_lim[1]-self.y_lim[0])/y_dim)*reduction
        else:
            scale_fac = abs(.99*(self.x_lim[1]-self.x_lim[0])/x_dim)*reduction
        origin_shift = np.array([[c_paths[0],c_paths[1]]])
        new_paths = []
        Pc = np.array([[(self.x_lim[1]+self.x_lim[0])/2, (self.y_lim[1]+self.y_lim[0])/2]])
        Shift = Pc - scale_fac*origin_shift
        if (paths is None):
            return []
        for p in paths:
            if (len(p)<2):
                continue
            A = np.array(p)*scale_fac + Shift
            new_paths.append(A.tolist())
        return new_paths
    #######
    # Basic Shapes.
    #######
    def draw_border(self):
        self.draw_rect(self.x_lim[0], self.x_lim[1], self.y_lim[0], self.y_lim[1])
        return
    def draw_rect(self, x0, x1, y0, y1):
        self.draw_vertices([[x0,y0],[x1,y0],[x1,y1],[x0,y1]], cycle=True)
    def draw_circle(self, X, Y, r = 0.5, n=20):
        verts = ngon(X, Y, r, n=20)
        self.draw_vertices(verts)
    def draw_cross(self, X,Y):
        self.draw_vertices([[X-self.cent, Y-self.cent], [X+self.cent, Y+self.cent]])
        self.draw_vertices([[X-self.cent, Y+self.cent], [X+self.cent, Y-self.cent]])
    def plot_raw_grid(self):
        """
        This allows you to calibrate the caternary
        correction.
        """
        for X in self.caternary.Xs:
            self.pen_up()
            self.move_to(X,self.caternary.Ys[0],raw=True)
            self.pen_down()
            for Y in self.caternary.Ys:
                self.move_to(X,Y,raw=True)
        for Y in self.caternary.Ys:
            self.pen_up()
            self.move_to(self.caternary.Xs[0],Y,raw=True)
            self.pen_down()
            for X in self.caternary.Xs:
                self.move_to(X,Y,raw=True)
        self.pen_up()
        return
    def plot_calibrate(self):
        print("Plotting calibration pattern....")
        print("Squares at 2cm increments around center.")
        print("Crosses NSEW in between.")
        self.draw_circle(*self.center)
        xc,yc = self.center
        x0 = xc-1
        y0 = yc-1
        x1 = xc+1
        y1 = yc+1
        NN = 1.
        while x0>self.x_lim[0] and x1<self.x_lim[1] and y0>self.y_lim[0] and y1<self.y_lim[1]:
            self.draw_rect(x0, x1, y0, y1)
            self.draw_cross(xc,y0+1.)
            self.draw_cross(xc,y1-1.)
            self.draw_cross(x0+1.,yc)
            self.draw_cross(x1-1.,yc)
            NN = NN+2.
            x0 = xc-NN
            y0 = yc-NN
            x1 = xc+NN
            y1 = yc+NN
        return
    def pre_process_file(self, filename):
        with open(filename,'rb') as f:
            DATA = pickle.load(f)
        OPATHS = self.pre_process(DATA)
        with open(filename.split('.')[0]+"_processed.pkl",'wb') as f:
            pickle.dump(OPATHS, f)
    def pre_process(self, DATA):
        """
        Rotates, scales, plans
        """
        # Determine the depth.
        # CYMK is 4 X paths X pts X 2
        # B/W is paths X pts X 2
        if depth(DATA)==4:
            OPATHS = [self.sched_paths(channel, self.cymk_bounds(DATA)) for channel in DATA]
            print("Scheduled paths.")
        else:
            OPATHS = self.sched_paths(DATA)
            print("Scheduled paths.")
        return OPATHS
    def plot_file(self, filename):
        """
        Only plots files in a raw format.
        They should have been pre-processed!
        """
        with open(filename,'rb') as f:
            DATA = pickle.load(f)
        # Determine the depth.
        # CYMK is 4 X paths X pts X 2
        # B/W is paths X pts X 2
        if depth(DATA)==4:
            print("Data Bounds: ", self.cymk_bounds(DATA))
            print("Scaling Data....")
            SDATA = [self.scale_paths(channel, self.cymk_bounds(DATA)) for channel in DATA]
            cbds = self.cymk_bounds(SDATA)
            print("Scaled Data to",cbds)
            if cbds[0]<self.x_lim[0]-.1 or cbds[1]<self.y_lim[0]-.1 or cbds[2]>self.x_lim[1]+.1 or cbds[3]>self.y_lim[1]+.1:
                print(cbds[0]<self.x_lim[0]-.1 , cbds[1]<self.y_lim[0]-.1 , cbds[2]>self.x_lim[1]+.1 , cbds[3]>self.y_lim[1]+.1)
                print("File Data oob, pre_process_file() plz.")
                return
            # TODO Rotate CYMK
            print("Ploting CYMK")
            print("Load Cyan")
            self.draw_paths(SDATA[0])
            print("Load Yellow")
            self.draw_paths(SDATA[1])
            print("Load Magenta")
            self.draw_paths(SDATA[2])
            print("Load Black")
            self.draw_paths(SDATA[3])
        else:
            # This is a monochrome plot.
            # Check the plot fits in the plot_area.
            # This is a monochrome plot.
            cbds = self.paths_bounds(DATA)
            print("Data Bounds: ",cbds)
            DATA = copy.copy(self.auto_rotate(DATA, cbds))
            print("Scaling Data....")
            SDATA = self.scale_paths(DATA, self.paths_bounds(DATA))
            cbds = self.paths_bounds(SDATA)
            print("Scaled Data to",cbds)
            if cbds[0]<self.x_lim[0] or cbds[1]<self.y_lim[0] or cbds[2]>self.x_lim[1] or cbds[3]>self.y_lim[1]:
                print("File Data oob, pre_process_file() plz.")
                return
            print("Data Bounds: ",cbds)
            print("Load Pen.")
            self.draw_paths(SDATA)
    def file_picker(self, path="./"):
        files = os.listdir(path)
        print("Line Files:")
        print("----------")
        for I,f in enumerate(files):
            if f.count('.pkl')>0:
                print(I,f)
        print("----------")
        print("--- Selection ---")
        K = int(input())
        return files[K]
    def choose_file(self):
        target_file = self.file_picker()
        self.plot_file(target_file)
        return
    def pre_process_files(self, path="./"):
        files = os.listdir(path)
        for I,f in enumerate(files):
            if f.count('.pkl')>0 and f.count('_processed')<1:
                print('processing:', f)
                self.pre_process_file(f)
        return

if __name__ == "__main__":
    pl = Plotter(test=False, repl=True)

from shapely.geometry import Point
from shapely.geometry.polygon import Polygon
import numpy as np

def get_field():
    points = [
        [150, 120],
        [800, 50],
        [1000, 600],
        [900, 700],
        [300, 750],
    ]
    return points


def get_grid(field, step):
    grid = []
    min_x = min((p[0] for p in field))
    min_y = min((p[1] for p in field))
    max_x = max((p[0] for p in field))
    max_y = max((p[1] for p in field))
    polygon = Polygon(field)

    for x in range(min_x, max_x, step):
        for y in range(min_y, max_y, step):
            point = Point(x, y)
            if polygon.contains(point):
                grid.append([x, y])
    return grid


def get_drones_initial_positions(field, grid):
    return [
        [100, 100],
        [1000, 700],
    ]

def get_grid_size(a):
    counters=[]
    
    counter=0
    for i in range(len(a)):
        if (i==(len(a)-1)):
            counter+=1
            counters.append(counter)
        else:
            if a[i][0]==a[i-1][0]:
                counter+=1        
            else:
                counter+=1
                counters.append(counter)
                counter=0
    #print(counters[1:])
    X_DIM=len(counters)
    Y_DIM=np.amax(counters[1:])
    return X_DIM, Y_DIM
    
    
    
def convert_coordinates(a):
    a=np.array(a)
    x,y=[],[]
    for b in a:
        x.append(b[0])
        y.append(b[1])
    return x,y
    
    
def get_zigzag_path(grid):
    X_DIM, Y_DIM =get_grid_size(grid)
    
    x,y=convert_coordinates(grid)
        
    min_x=min(x)
    max_x=max(x)

    min_y=min(y)
    max_y=max(y)

    nx=np.linspace(min_x,max_x,X_DIM)
    ny=np.linspace(min_y,max_y,Y_DIM)
    zr=np.meshgrid(nx,ny)
    
    new_coords=[]
    coord=()
    counter=0

    for i in range(Y_DIM):
        for j in range(X_DIM):

            for g in range(len(grid)):
                if i%2==0:
                    nj=j
                else:
                    nj=X_DIM-j-1

                if (grid[g][0] == int(zr[0][i][nj])) and (grid[g][1] == int(zr[1][i][nj])):
                    coord=[int(zr[0][i][nj]),int(zr[1][i][nj])]
                    #coord=[a[g][0],a[g][1]]
                    new_coords.append(coord)
                    coord=[]
                counter+=1
      
    print(get_grid_size(grid))
    return new_coords



def get_waypoints(field, grid, drones_inits):
    print('nz2')
    z=get_zigzag_path(grid)
    print(z)
    return [
        z[len(z)//2:],
        z[:len(z)//2]
    ]

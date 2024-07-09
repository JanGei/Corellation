import flopy
import numpy as np
import sys
from dependencies.conditional_k import conditional_k
from dependencies.Kriging import Kriging


sys.path.append('..')

class MFModel:
    
    def __init__(self, direc: str,  pars, obs_cid, maxcl = [], l_angs = [], ellips = []):
        self.direc      = direc
        self.mname      = pars['mname']
        self.pars       = pars
        self.sim        = flopy.mf6.modflow.MFSimulation.load(
                                version             = 'mf6', 
                                exe_name            = 'mf6',
                                sim_ws              = direc, 
                                verbosity_level     = 0
                                )
        self.gwf        = self.sim.get_model(self.mname)
        self.npf        = self.gwf.npf
        self.rch        = self.gwf.rch
        self.riv        = self.gwf.riv
        self.wel        = self.gwf.wel
        self.ic         = self.gwf.ic
        self.chd        = self.gwf.chd
        self.mg         = self.gwf.modelgrid
        self.cxy        = np.vstack((self.mg.xyzcellcenters[0], self.mg.xyzcellcenters[1])).T
        self.dx         = pars['dx']
        self.old_npf    = []
        self.n_failure  = 0
        self.n_neg_def  = 0
        self.obs_cid    = [int(i) for i in obs_cid]
        if pars['pilotp']:
            self.ellips_mat = np.array([[ellips[0], ellips[1]], [ellips[1], ellips[2]]])
            self.lx         = [l_angs[0], l_angs[1]]
            self.ang        = l_angs[2]
            self.a          = 0.33
            self.corrL_max  = np.min(pars['nx'] * pars['dx'])
            self.threshhold = self.corrL_max * self.a
                     
                       
    def simulation(self):
        success, buff = self.sim.run_simulation()
        if not success:
            self.set_field([self.old_npf], ['npf'])
            self.sim.run_simulation()
            self.n_failure += 1
       
    def update_ic(self):
        self.ic.strt.set_data(self.get_field('h')['h'])
        self.ic.write()
       
    def Kalman_vec(self, h_mask, pp_cid = []):
        data = self.get_field(['h', 'npf', 'cov_data'])
        
        ysim = np.squeeze(data['h'][self.obs_cid])
        h_nobc = data['h'][~h_mask]

        if 'cov_data' in self.pars['EnKF_p']:
            if 'npf' in self.pars['EnKF_p']:
                x = np.concatenate([data['cov_data'], np.log(data['npf'][pp_cid]), h_nobc])
            else:
                x = np.concatenate([data['cov_data'], h_nobc])
        else:
            if self.pars['pilot_p']:
                x = np.concatenate([np.log(data['npf'][pp_cid]), h_nobc])
            else:
                x = np.concatenate([data['npf'], h_nobc])
    
        return x, ysim
        
    def apply_x(self, x, h_mask, pp_xy, pp_cid, mean_cov_par, var_cov_par):
        
        data = self.get_field(['h', 'npf', 'cov_data'])
        cl = 3

        if 'cov_data' in self.pars['EnKF_p']:
            if 'npf' in self.pars['EnKF_p']:
                data['h'][~h_mask] = x[self.pars['n_PP']+cl:]
                res = self.kriging([x[0:cl], x[cl:self.pars['n_PP']+cl]],
                                   pp_xy,
                                   pp_cid,
                                   mean_cov_par,
                                   var_cov_par)
            else:
                data['h'][~h_mask] = x[cl:]
                res = self.kriging([x[0:cl], x[cl:self.pars['n_PP']+cl]],
                                   pp_xy,
                                   pp_cid,
                                   mean_cov_par,
                                   var_cov_par)
        else:
            if self.pars['pilot_p']:
                data['h'][~h_mask] = x[self.pars['n_PP']:]
              
                field = conditional_k(self.cxy,
                                      self.dx,
                                      self.lx,
                                      self.ang,
                                      self.pars['sigma'][0],
                                      self.pars,
                                      np.exp(x[0:self.pars['n_PP']:]),
                                      pp_xy,
                                      )
                
                self.set_field([np.exp(field)], ['npf'])
            # else:
                # THIS NEEDS TO BE REVISED - EnKF without PP
                # data['h'][~h_mask] = x[self.pars['nPP']+cl:]
                # self.kriging()
        
        self.set_field([data['h']], ['h'])
    
        return res
    
    def kriging(self, data, pp_xy, pp_cid, mean_cov_par, var_cov_par):
  
        mat, pos_def = self.check_new_matrix(data[0])
        
        if pos_def:
            l1, l2, angle = self.pars['mat2cv'](mat)    
            l1, l2, angle = self.check_vario(l1,l2, angle)
            
            pp_k = data[1]
            
            if self.pars['condfl']:
                field = conditional_k(self.cxy,
                                      self.dx,
                                      self.lx,
                                      self.ang,
                                      self.pars['sigma'][0],
                                      self.pars,
                                      pp_k,
                                      pp_xy,
                                      )
            else:
                field = Kriging(self.cxy,
                                self.dx,
                                self.lx,
                                self.ang,
                                self.pars['sigma'][0],
                                self.pars,
                                pp_k,
                                pp_xy)
            
            self.set_field([field[0]], ['npf'])
            
        else:
            l1, l2, angle = self.pars['mat2cv'](self.ellips_mat)
            self.n_neg_def += 1 
            if self.n_neg_def == 10:
                self.replace_model(mean_cov_par, var_cov_par, pp_xy, pp_cid)
                
        return [[l1, l2, angle], [self.ellips_mat[0,0], self.ellips_mat[1,0], self.ellips_mat[1,1]], pos_def]
                    
    
    def update_ellips_mat(self, mat):
        self.ellips_mat = mat.copy()
     
    def replace_model(self, mean_cov_par, var_cov_par, pp_xy, pp_cid):
        pos_def = False
        while not pos_def:
            a = np.random.normal(mean_cov_par[0,0], np.sqrt(var_cov_par[0,0]))
            m = np.random.normal(mean_cov_par[0,1], np.sqrt(var_cov_par[0,1]))
            b = np.random.normal(mean_cov_par[1,1], np.sqrt(var_cov_par[1,1]))
        
            eigenvalues, eigenvectors, mat, pos_def = self.check_new_matrix([a,m,b])
        self.n_neg_def == 0    
        l1, l2, angle = self.kriging([mat[0,0], mat[1,0], mat[1,1]], pp_xy, pp_cid, mean_cov_par, var_cov_par)
    
    
    def check_new_matrix(self, data):
        
        mat = np.diag([data[0], data[2]]) + data[1] * (1 - np.eye(2))
        eigenvalues, eigenvectors = np.linalg.eig(mat)
        
        #check for positive definiteness
        if np.all(eigenvalues > 0):
            pos_def = True
        else:
            pos_def = False
            
        if not pos_def:
            reduction = 0.96
            difmat = mat - self.ellips_mat
            while reduction > 0:
                test_mat = self.ellips_mat + reduction * difmat
                eigenvalues, eigenvectors = np.linalg.eig(test_mat)
                if np.all(eigenvalues > 0):
                    pos_def = True
                    mat = test_mat
                    break
                else:
                    reduction -= 0.05
        
        if pos_def:
            self.update_ellips_mat(mat)
            
        return mat, pos_def

            
    def reduce_corL(self, corL):
        # reducing correlation lengths based on monod kinetic model
        return (self.corrL_max * corL) / (self.corrL_max*(1-self.a) + corL)
        
    def check_vario(self, l1, l2, angle):
        correction = False
        
        if l2 > l1:
            correction = True
            l1, l2 = l2, l1
            angle = angle + np.pi/2
            print("It happened")
            
        if l1 > self.threshhold:
            l1 = self.reduce_corL(l1)
            correction = True
            
        if l2 > self.threshhold:
            l2 = self.reduce_corL(l2)
            correction = True
            
        while angle > np.pi/2:
            angle -= np.pi
            correction = True
        while angle < -np.pi/2:
            angle += np.pi
            correction = True
            
        if correction:
            self.variogram_to_matrix(l1, l2, angle)
        
        self.lx = [l1, l2]
        self.ang = angle
        
        return l1, l2, angle
    
    def variogram_to_matrix(self, l1, l2, angle):
        D = self.pars['rotmat'](angle)
        M = D @ np.array([[1/l1**2, 0],[0, 1/l2**2]]) @ D.T
        self.update_ellips_mat(M)
        
        
    def set_field(self, field, pkg_name: list):
        for i, name in enumerate(pkg_name):
            if name == 'npf':
                self.old_npf =  self.npf.k.get_data()
                self.npf.k.set_data(np.reshape(field[i],self.npf.k.array.shape))
                self.npf.write()
            elif name == 'rch':
                self.rch.stress_period_data.set_data(field[i])
                self.rch.write()
            elif name == 'riv':
                self.riv.stress_period_data.set_data(field[i])
                self.riv.write()
            elif name == 'wel':
                self.wel.stress_period_data.set_data(field[i])
                self.wel.write()
            elif name == 'h':
                self.ic.strt.set_data(field[i])
                self.ic.write()
            else:
                print(f'The package {name} that you requested is not part of the model')
            
        
    def get_field(self, pkg_name: list) -> dict:
        fields = {}
        for name in pkg_name:
            if name == 'npf':
                fields.update({name:np.squeeze(self.npf.k.get_data())})
            elif name == 'rch':
                fields.update({name:self.rch.stress_period_data.get_data()})
            elif name == 'riv':
                fields.update({name:self.riv.stress_period_data.get_data()})
            elif name == 'wel':
                fields.update({name:self.wel.stress_period_data.get_data()})
            elif name == 'chd':
                fields.update({name:self.chd.stress_period_data.get_data()})
            elif name == 'h':
                fields.update({name:np.squeeze(self.gwf.output.head().get_data())})
            elif name == 'ic':
                fields.update({name:np.squeeze(self.ic.strt.get_data())})
            elif name == 'cov_data':
                fields.update({name:np.array([self.ellips_mat[0,0],
                                              self.ellips_mat[0,1],
                                              self.ellips_mat[1,1]])})
            else:
                print(f'The package {name} that you requested is not part of the model')
                
        return fields
        
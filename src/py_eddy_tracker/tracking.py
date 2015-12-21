# -*- coding: utf-8 -*-
"""
===========================================================================
This file is part of py-eddy-tracker.

    py-eddy-tracker is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    py-eddy-tracker is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with py-eddy-tracker.  If not, see <http://www.gnu.org/licenses/>.

Copyright (c) 2014-2015 by Evan Mason
Email: emason@imedea.uib-csic.es
===========================================================================


py_eddy_tracker_amplitude.py

Version 2.0.3

===========================================================================

"""
from py_eddy_tracker.observations import EddiesObservations, \
    VirtualEddiesObservations, TrackEddiesObservations
from numpy import bool_, array, arange, ones, setdiff1d, zeros, uint16
import logging


class Correspondances(list):
    """Object to store correspondances
    And run tracking
    """
    UINT32_MAX = 4294967295
    # Prolongation limit to 255
    VIRTUAL_DTYPE = 'u1'
    # ID limit to 4294967295
    ID_DTYPE = 'u4'
    # Track limit to 65535
    N_DTYPE = 'u2'


    def __init__(self, datasets, virtual=0):
        """Initiate tracking
        """
        # Correspondance dtype
        self.correspondance_dtype = [('in', 'u2'),
                                     ('out', 'u2'),
                                     ('id', self.ID_DTYPE)]
        # To count ID
        self.current_id = 0
        # Dataset to iterate
        self.datasets = datasets
        self.previous2_obs = None
        self.previous_obs = None
        self.current_obs = EddiesObservations.load_from_netcdf(
            self.datasets[0])
        
        # To use virtual obs
        # Number of obs which can prolongate real observations
        self.nb_virtual = virtual
        # Activation or not
        self.virtual = virtual > 0
        self.virtual_obs = None
        self.previous_virtual_obs = None
        if self.virtual:
            # Add field to dtype to follow virtual observations
            self.correspondance_dtype += [
                ('virtual', bool_),
                ('virtual_length', self.VIRTUAL_DTYPE)]
        
        # Array to simply merged
        self.nb_obs_by_tracks = None
        self.i_current_by_tracks = None
        self.nb_obs = 0
        self.eddies = None

    def swap_dataset(self, dataset):
        """
        """
        self.previous2_obs = self.previous_obs
        self.previous_obs = self.current_obs
        self.current_obs = EddiesObservations.load_from_netcdf(dataset)
        
    def store_correspondance(self, i_previous, i_current):
        correspondance = array(
            i_previous,
            dtype=self.correspondance_dtype)
        correspondance['out'] = i_current

        if self.virtual:
            correspondance['virtual'] = i_previous >= nb_real_obs
    
    def id_generator(self, nb_id):
        """Generation id and incrementation
        """
        values = arange(self.current_id, self.current_id + nb_id)
        self.current_id += nb_id
        return values
    
    def recense_dead_id_to_extend(self):
        """Recense dead id to extend in virtual observation
        """
        nb_virtual_extend = 0
        # List previous id which are not use in the next step
        dead_id = setdiff1d(self[-2]['id'], self[-1]['id'])
        nb_dead = dead_id.shape[0]
        logging.debug('%d death of real obs in this step', nb_dead)
        if not self.virtual:
            return
        # Creation of an virtual step for dead one
        self.virtual_obs = VirtualEddiesObservations(size=nb_dead + nb_virtual_extend)

        # Find mask/index on previous correspondance to extrapolate
        # position
        list_previous_id = self[-2]['id'].tolist()
        i_dead_id = [list_previous_id.index(i) for i in dead_id]

        # Selection of observations on N-2 and N-1
        obs_a = self.previous2_obs.obs[self[-2][i_dead_id]['in']]
        obs_b = self.previous_obs.obs[self[-2][i_dead_id]['out']]
        # Position N-2 : A
        # Position N-1 : B
        # Virtual Position : C
        # New position C = B + AB
        self.virtual_obs['dlon'][:nb_dead] = obs_b['lon'] - obs_a['lon']
        self.virtual_obs['dlat'][:nb_dead] = obs_b['lat'] - obs_a['lat']
        self.virtual_obs['lon'][:nb_dead
            ] = obs_b['lon'] + self.virtual_obs['dlon'][:nb_dead]
        self.virtual_obs['lat'][:nb_dead
            ] = obs_b['lat'] + self.virtual_obs['dlat'][:nb_dead]
        # Id which are extended
        self.virtual_obs['track'][:nb_dead] = dead_id
        # Add previous virtual
        if nb_virtual_extend > 0:
            obs_to_extend = self.previous_virtual_obs.obs[i_virtual_dead_id][alive_virtual_obs]
            self.virtual_obs['lon'][nb_dead:] = obs_to_extend['lon'] + obs_to_extend['dlon']
            self.virtual_obs['lat'][nb_dead:] = obs_to_extend['lat'] + obs_to_extend['dlat']
            self.virtual_obs['track'][nb_dead:] = obs_to_extend['track']
            self.virtual_obs['segment_size'][nb_dead:] = obs_to_extend['segment_size']
        # Count
        self.virtual_obs['segment_size'][:] += 1
    
    def track(self):
        """Run tracking
        """
        START = True
        FLG_VIRTUAL = False
        # We begin with second file, first one is in previous
        for file_name in self.datasets[1:]:
            self.swap_dataset(file_name)
            logging.debug('%s match with previous state', file_name)
            logging.debug('%d obs to match', len(self.current_obs))
        
            nb_real_obs = len(self.previous_obs)
            if FLG_VIRTUAL:
                logging.debug('%d virtual obs will be add to previous',
                              len(self.virtual_obs))
                # If you comment this the virtual fonctionnality will be disable
                self.previous_obs = self.previous_obs.merge(self.virtual_obs)
        
            i_previous, i_current = self.previous_obs.tracking(self.current_obs)
            nb_match = i_previous.shape[0]

            #~ self.store_correspondance(i_previous, i_current)
            correspondance = array(i_previous, dtype=self.correspondance_dtype)
            correspondance['out'] = i_current
            
            if self.virtual:
                correspondance['virtual'] = i_previous >= nb_real_obs
                
            if START:
                START = False
                # Set an id for each match
                correspondance['id'] = self.id_generator(nb_match)
                self.append(correspondance)
                continue

            # We set all id to UINT32_MAX
            id_previous = ones(len(self.previous_obs), dtype=self.ID_DTYPE) * self.UINT32_MAX
            # We get old id for previously eddies tracked
            previous_id = self[-1]['id']
            id_previous[self[-1]['out']] = previous_id
            correspondance['id'] = id_previous[correspondance['in']]

            if FLG_VIRTUAL:
                nb_rebirth = correspondance['virtual'].sum()
                if nb_rebirth != 0:
                    logging.debug('%d re-birth due to prolongation with'
                                  ' virtual observations', nb_rebirth)
                    # Set id for virtual
                    i_virtual = correspondance['in'][correspondance['virtual']] - nb_real_obs
                    correspondance['id'][correspondance['virtual']] = \
                        self.virtual_obs['track'][i_virtual]
                    correspondance['virtual_length'][correspondance['virtual']] = \
                        self.virtual_obs['segment_size'][i_virtual]
            
            # new_id is equal to UINT32_MAX we must add a new ones
            # we count the number of new
            mask_new_id = correspondance['id'] == UINT32_MAX
            nb_new_tracks = mask_new_id.sum()
            logging.debug('%d birth in this step', nb_new_tracks)
            # Set new id
            correspondance['id'][mask_new_id] = self.id_generator(nb_new_tracks)

            self.append(correspondance)

            # SECTION for virtual observation
            nb_virtual_prolongate = 0
            if FLG_VIRTUAL:
                # Save previous state to count virtual obs
                self.previous_virtual_obs = self.virtual_obs
                virtual_dead_id = setdiff1d(self.virtual_obs['track'],
                                            correspondance['id'])
                list_previous_virtual_id = self.virtual_obs['track'].tolist()
                i_virtual_dead_id = [
                    list_previous_virtual_id.index(i) for i in virtual_dead_id]
                # Virtual obs which can be prolongate
                alive_virtual_obs = self.virtual_obs['segment_size'][i_virtual_dead_id] < self.nb_virtual
                nb_virtual_prolongate = alive_virtual_obs.sum()
                logging.debug('%d virtual obs will be prolongate on the '
                              'next step', nb_virtual_prolongate)

            self.recense_dead_id_to_extend()

            if self.virtual:
                FLG_VIRTUAL = True

    def prepare_merging(self):
        # count obs by tracks (we add directly one, because correspondance
        # is an interval)
        self.nb_obs_by_tracks = zeros(self.current_id, dtype=self.N_DTYPE) + 1
        for correspondance in self:
            self.nb_obs_by_tracks[correspondance['id']] += 1
            if self.virtual:
                # When start is virtual, we don't have a previous correspondance
                self.nb_obs_by_tracks[correspondance['id'][correspondance['virtual']]
                                 ] += correspondance['virtual_length'][correspondance['virtual']]

        # Compute index of each tracks
        self.i_current_by_tracks = self.nb_obs_by_tracks.cumsum() - self.nb_obs_by_tracks
        # Number of global obs
        self.nb_obs = nb_obs_by_tracks.sum()
        logging.info('%d tracks identified', self.current_id)
        logging.info('%d observations will be join', self.nb_obs)

    def merge(self):
        # Start create netcdf to agglomerate all eddy
        self.eddies = TrackEddiesObservations(size=self.nb_obs)

        # Calculate the index in each tracks, we compute in u4 and translate
        # in u2 (which are limited to 65535)
        logging.debug('Compute global index array (N)')
        n = arange(nb_obs,
                   dtype='u4') - self.i_current_by_tracks.repeat(self.nb_obs_by_tracks)
        self.eddies['n'][:] = uint16(n)
        logging.debug('Compute global track array')
        self.eddies['track'][:] = arange(self.current_id).repeat(self.nb_obs_by_tracks)

        # Start loading identification again to save in the finals tracks
        # Load first file
        eddies_previous = EddiesObservations.load_from_netcdf(self.datasets[0])
        # Set type of eddy with first file
        self.eddies.sign_type = eddies_previous.sign_type

        # To know if the track start
        first_obs_save_in_tracks = zeros(i_current_by_tracks.shape,
                                            dtype=bool_)

        for i, file_name in enumerate(FILENAMES[1:]):
            # Load current file (we begin with second one)
            self.current_obs = EddiesObservations.load_from_netcdf(file_name)
            # We select the list of id which are involve in the correspondance
            i_id = self[i]['id']
            # Index where we will write in the final object
            index_final = i_current_by_tracks[i_id]

            # First obs of eddies
            m_first_obs = -first_obs_save_in_tracks[i_id]
            if m_first_obs.any():
                # Index in the current file
                index_in = self[i]['in'][m_first_obs]
                # Copy all variable
                for var, _ in eddies_current.obs.dtype.descr:
                    self.eddies[var][index_final[m_first_obs]
                        ] = eddies_previous[var][index_in]
                # Increment
                i_current_by_tracks[i_id[m_first_obs]] += 1
                # Active this flag, we have only one first by tracks
                first_obs_save_in_tracks[i_id] = True
                index_final = i_current_by_tracks[i_id]

            # Index in the current file
            index_current = self[i]['out']
            
            if self.virtual:
                # If the flag virtual in correspondance is active,
                # the previous is virtual
                m_virtual = self[i]['virtual']
                if m_virtual.any():
                    index_virtual = index_final[m_virtual]
                    # Incrementing index
                    i_current_by_tracks[i_id[m_virtual]
                        ] += self[i]['virtual_length'][m_virtual]
                    # Get new index
                    index_final = i_current_by_tracks[i_id]

            # Copy all variable
            for var, _ in eddies_current.obs.dtype.descr:
                self.eddies[var][index_final
                    ] = eddies_current[var][index_current]

            # Add increment for each index used
            i_current_by_tracks[i_id] += 1
            eddies_previous = eddies_current

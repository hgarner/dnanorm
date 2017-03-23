import csv
import os
import re

class PlateSet:
  
  def __init__(self):
    self.plate_cols = 12
    self.plate_rows = 8
    self.plate_start_chars = '<>'
    self.csv_delim = '\t'
    self.plates = []
    self.start_metadata = []
    self.end_metadata = []
    self.filename = None

  def processCsv(self, csv_file):
    csv_file = open(csv_file, 'r', encoding='latin-1')
    self.filename = csv_file

    with csv_file:
      reader = csv.reader(csv_file, delimiter=self.csv_delim)
      plate = None
      plate_row = 0
      for line in reader:
        if plate is None and line[0] != self.plate_start_chars:
          if len(self.plates) == 0:
            #we haven't started a plate yet, so stick this data in self.start_metadata
            self.start_metadata.append('\t'.join(line))
          else:
            #this assumes that there's no metadata between plates. if this is not so, this will include it in the end_metadata.
            self.end_metadata.append('\t'.join(line))
        if plate_row > self.plate_rows:
          #if we've filled the plate, append copy to self.plates and reset
          self.plates.append(deepcopy(plate))
          plate = None
          plate_row = 0
        if line[0] == self.plate_start_chars:
          #if this is the start a a new plate, reset plate and row to beginning
          plate = {}
          plate_row = 1
          continue
        elif plate is not None:
          if len(line) < self.plate_cols:
            #do we have enough columns?
            if plate_row == 1 and len(plate.keys()) == 0:
              #skip as non-plate data
              continue
            else:
              #otherwise we have a problem
              raise ValueError('Not enough colums in row {plate_row}, plate {plate_no}'.format(plate_row=plate_row, plate_no=len(self.plates)))
          if len(line) > self.plate_cols:
            #we might have too many columns
            #if the last is empty and we only have a single value more than self.plate_cols 
            #(note that the first col is the row label), we can ignore
            #todo add option to turn this off
            if line[-1] == '' and len(line) == self.plate_cols + 2:
              line = line[:-1]
            else:
              #otherwise we have a problem - too many columns and/or the last is not empty
              raise ValueError('Too many colums in row {plate_row}, plate {plate_no}'.format(plate_row=plate_row, plate_no=len(self.plates)))
          for well in enumerate(line):
            if well[0] != 0:
              location = '{row}{col:02}'.format(row=line[0], col=well[0])
              try:
                #add data to plate location 
                #convert to float
                plate[location] = float(well[1])
              except ValueError:
                #if float conversion fails, try int
                #possibly not ideal as we'll have a mix of types
                try:
                  plate[location] = int(well[1])
                except ValueError:
                  plate[location] = well[1]
              
          plate_row += 1

              
    return self.plates


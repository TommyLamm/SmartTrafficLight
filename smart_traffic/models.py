from ultralytics import YOLO

from .config import CAR_MODEL_PATH, PERSON_MODEL_PATH, PLATE_MODEL_PATH


print("Loading Car Detection Model...")
car_model = YOLO(CAR_MODEL_PATH)

print("Loading Person/Wheelchair Detection Model...")
person_model = YOLO(PERSON_MODEL_PATH)

print("Loading Licence Plate Detection Model...")
plate_model = YOLO(PLATE_MODEL_PATH)

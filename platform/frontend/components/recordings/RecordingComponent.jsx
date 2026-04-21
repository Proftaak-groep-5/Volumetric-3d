//Component for viewing all recordings in the database.
import React, { useState, useEffect } from 'react';
import { getAllRecordings } from '../../services/recordingService';
import RecordingCard from './RecordingCard';
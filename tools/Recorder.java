package com.pisar;

import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import java.io.File;
import java.io.FileOutputStream;
import java.io.RandomAccessFile;

public class Recorder {
    private static final int SAMPLE_RATE = 16000;
    private static final int CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO;
    private static final int AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT;

    public static void main(String[] args) {
        if (args.length < 1) {
            System.err.println("Usage: app_process / com.pisar.Recorder <output.wav>");
            System.exit(1);
        }

        String outputPath = args[0];
        int bufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT);
        if (bufferSize <= 0) bufferSize = 4096;

        AudioRecord recorder = null;
        try {
            recorder = new AudioRecord(
                MediaRecorder.AudioSource.MIC,
                SAMPLE_RATE,
                CHANNEL_CONFIG,
                AUDIO_FORMAT,
                bufferSize * 2
            );

            if (recorder.getState() != AudioRecord.STATE_INITIALIZED) {
                System.err.println("Error: AudioRecord not initialized");
                System.exit(2);
            }

            File outFile = new File(outputPath);
            FileOutputStream fos = new FileOutputStream(outFile);
            writeWavHeader(fos, 0);

            recorder.startRecording();
            byte[] buffer = new byte[bufferSize];
            int totalBytes = 0;

            final AudioRecord rec = recorder;
            final File finalFile = outFile;
            final int[] totalRef = new int[]{0};

            Runtime.getRuntime().addShutdownHook(new Thread(new Runnable() {
                public void run() {
                    try {
                        rec.stop();
                        rec.release();
                        updateWavHeader(finalFile, totalRef[0]);
                    } catch (Exception ignored) {}
                }
            }));

            while (!Thread.currentThread().isInterrupted()) {
                int read = recorder.read(buffer, 0, buffer.length);
                if (read > 0) {
                    fos.write(buffer, 0, read);
                    totalBytes += read;
                    totalRef[0] = totalBytes;
                }
            }

            fos.close();
            recorder.stop();
            recorder.release();
            updateWavHeader(outFile, totalBytes);
        } catch (Exception e) {
            e.printStackTrace();
            System.exit(1);
        }
    }

    private static void writeWavHeader(FileOutputStream out, int audioLength) throws Exception {
        byte[] header = new byte[44];
        long totalDataLen = audioLength + 36;
        long byteRate = SAMPLE_RATE * 2;

        header[0] = 'R'; header[1] = 'I'; header[2] = 'F'; header[3] = 'F';
        header[4] = (byte) (totalDataLen & 0xff);
        header[5] = (byte) ((totalDataLen >> 8) & 0xff);
        header[6] = (byte) ((totalDataLen >> 16) & 0xff);
        header[7] = (byte) ((totalDataLen >> 24) & 0xff);
        header[8] = 'W'; header[9] = 'A'; header[10] = 'V'; header[11] = 'E';
        header[12] = 'f'; header[13] = 'm'; header[14] = 't'; header[15] = ' ';
        header[16] = 16; header[17] = 0; header[18] = 0; header[19] = 0;
        header[20] = 1; header[21] = 0;
        header[22] = 1; header[23] = 0;
        header[24] = (byte) (SAMPLE_RATE & 0xff);
        header[25] = (byte) ((SAMPLE_RATE >> 8) & 0xff);
        header[26] = (byte) ((SAMPLE_RATE >> 16) & 0xff);
        header[27] = (byte) ((SAMPLE_RATE >> 24) & 0xff);
        header[28] = (byte) (byteRate & 0xff);
        header[29] = (byte) ((byteRate >> 8) & 0xff);
        header[30] = (byte) ((byteRate >> 16) & 0xff);
        header[31] = (byte) ((byteRate >> 24) & 0xff);
        header[32] = 2; header[33] = 0;
        header[34] = 16; header[35] = 0;
        header[36] = 'd'; header[37] = 'a'; header[38] = 't'; header[39] = 'a';
        header[40] = (byte) (audioLength & 0xff);
        header[41] = (byte) ((audioLength >> 8) & 0xff);
        header[42] = (byte) ((audioLength >> 16) & 0xff);
        header[43] = (byte) ((audioLength >> 24) & 0xff);

        out.write(header, 0, 44);
    }

    private static void updateWavHeader(File file, int audioLength) {
        try (RandomAccessFile raf = new RandomAccessFile(file, "rw")) {
            long totalDataLen = audioLength + 36;
            raf.seek(4);
            raf.write((byte) (totalDataLen & 0xff));
            raf.write((byte) ((totalDataLen >> 8) & 0xff));
            raf.write((byte) ((totalDataLen >> 16) & 0xff));
            raf.write((byte) ((totalDataLen >> 24) & 0xff));
            raf.seek(40);
            raf.write((byte) (audioLength & 0xff));
            raf.write((byte) ((audioLength >> 8) & 0xff));
            raf.write((byte) ((audioLength >> 16) & 0xff));
            raf.write((byte) ((audioLength >> 24) & 0xff));
        } catch (Exception ignored) {}
    }
}

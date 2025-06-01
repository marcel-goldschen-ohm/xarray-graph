% Requires ADInstruments (LabChart) SDK by Jim Hokanson
% Available in MATLAB Add-Ons or at https://github.com/JimHokanson/adinstruments_sdk_matlab
% !!! ONLY works on Windows !!!

adiFile = adi.readFile;

[path, file, ext] = fileparts(adiFile.file_path);

% current and voltage recordings for each of two TEVC rigs (left and right)
IL = adiFile.getChannelByName('IL'); % channel 0
VL = adiFile.getChannelByName('VL'); % channel 1
IR = adiFile.getChannelByName('IR'); % channel 2
VR = adiFile.getChannelByName('VR'); % channel 3

for i = 1:adiFile.n_records
    % recording from left rig
    data = struct;
    data.current = IL.getData(i);
    data.current_units = IL.units{i};
    data.voltage = VL.getData(i);
    data.voltage_units = VL.units{i};
    data.time_interval_sec = IL.dt(i);
    data.events = struct.empty;
    for j = 1:length(adiFile.records(i).comments)
        comment = adiFile.records(i).comments(j);
        if comment.channel == -1 || comment.channel == 0
            data.events(end+1).text = comment.str;
            data.events(end).time_sec = comment.time;
        end
    end
    filename = fullfile(path, [file '_L']);
    if adiFile.n_records > 1
        filename = [filename '_' num2str(i)];
    end
    save(filename, '-struct', 'data');

    % recording from right rig
    data = struct;
    data.current = IR.getData(i);
    data.current_units = IR.units{i};
    data.voltage = VR.getData(i);
    data.voltage_units = VR.units{i};
    data.time_interval_sec = IR.dt(i);
    data.events = struct.empty;
    for j = 1:length(adiFile.records(i).comments)
        comment = adiFile.records(i).comments(j);
        if comment.channel == -1 || comment.channel == 2
            data.events(end+1).text = comment.str;
            data.events(end).time_sec = comment.time;
        end
    end
    filename = fullfile(path, [file '_R']);
    if adiFile.n_records > 1
        filename = [filename '_' num2str(i)];
    end
    save(filename, '-struct', 'data');
end

--[[
    AutoEditor — плагин автомонтажа для DaVinci Resolve Studio
    Единый Lua-скрипт: все 10 шагов, конфигурация, UI.
    Запуск: Workspace > Scripts > AutoEditor > main

    Зависимости: ffmpeg (в PATH), curl (для AI), DaVinci Resolve Studio 18+
]]

local PLUGIN_DIR = (debug.getinfo(1, "S").source:match("@(.*)") or ""):match("(.*/)")
    or (io.popen("pwd"):read("*l") .. "/")

--------------------------------------------------------------------------------
-- JSON (встроенный минимальный парсер/генератор)
--------------------------------------------------------------------------------
local json = {}

local function json_encode_value(val, indent, level)
    local t = type(val)
    if val == nil then return "null"
    elseif t == "boolean" then return tostring(val)
    elseif t == "number" then
        if val ~= val then return "null" end
        if val >= math.huge then return "1e999" end
        if val <= -math.huge then return "-1e999" end
        return string.format("%.14g", val)
    elseif t == "string" then
        local s = val:gsub('\\', '\\\\'):gsub('"', '\\"')
            :gsub('\n', '\\n'):gsub('\r', '\\r'):gsub('\t', '\\t')
        return '"' .. s .. '"'
    elseif t == "table" then
        level = level or 0
        local is_array = (#val > 0) or next(val) == nil
        -- Проверка, массив ли это
        if is_array then
            local count = 0
            for _ in pairs(val) do count = count + 1 end
            if count ~= #val then is_array = false end
        end

        local parts = {}
        local nl = indent and "\n" or ""
        local sp = indent and string.rep("  ", level + 1) or ""
        local sp_close = indent and string.rep("  ", level) or ""
        local sep = indent and ",\n" or ","

        if is_array then
            for i = 1, #val do
                parts[#parts + 1] = sp .. json_encode_value(val[i], indent, level + 1)
            end
            if #parts == 0 then return "[]" end
            return "[" .. nl .. table.concat(parts, sep) .. nl .. sp_close .. "]"
        else
            local keys = {}
            for k in pairs(val) do keys[#keys + 1] = k end
            table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
            for _, k in ipairs(keys) do
                parts[#parts + 1] = sp .. '"' .. tostring(k) .. '": '
                    .. json_encode_value(val[k], indent, level + 1)
            end
            if #parts == 0 then return "{}" end
            return "{" .. nl .. table.concat(parts, sep) .. nl .. sp_close .. "}"
        end
    end
    return "null"
end

function json.encode(val, pretty)
    return json_encode_value(val, pretty, 0)
end

function json.decode(str)
    if not str or str == "" then return nil end
    local pos = 1
    local function skip_ws()
        pos = str:find("[^ \t\n\r]", pos) or (#str + 1)
    end
    local function peek() skip_ws(); return str:sub(pos, pos) end
    local function next_char() skip_ws(); local c = str:sub(pos, pos); pos = pos + 1; return c end
    local parse_value

    local function parse_string()
        pos = pos + 1 -- skip opening "
        local start = pos
        local parts = {}
        while pos <= #str do
            local c = str:sub(pos, pos)
            if c == '"' then
                parts[#parts + 1] = str:sub(start, pos - 1)
                pos = pos + 1
                local result = table.concat(parts)
                result = result:gsub("\\n", "\n"):gsub("\\r", "\r"):gsub("\\t", "\t")
                    :gsub('\\"', '"'):gsub("\\\\", "\\"):gsub("\\/", "/")
                return result
            elseif c == '\\' then
                parts[#parts + 1] = str:sub(start, pos - 1)
                pos = pos + 2
                start = pos
            else
                pos = pos + 1
            end
        end
        return table.concat(parts)
    end

    local function parse_number()
        local ns = str:match("^%-?%d+%.?%d*[eE]?[%+%-]?%d*", pos)
        if ns then pos = pos + #ns; return tonumber(ns) end
        return 0
    end

    local function parse_array()
        pos = pos + 1 -- skip [
        local arr = {}
        skip_ws()
        if str:sub(pos, pos) == "]" then pos = pos + 1; return arr end
        while true do
            arr[#arr + 1] = parse_value()
            skip_ws()
            local c = next_char()
            if c == "]" then return arr end
        end
    end

    local function parse_object()
        pos = pos + 1 -- skip {
        local obj = {}
        skip_ws()
        if str:sub(pos, pos) == "}" then pos = pos + 1; return obj end
        while true do
            skip_ws()
            local key = parse_string()
            skip_ws(); pos = pos + 1 -- skip :
            obj[key] = parse_value()
            skip_ws()
            local c = next_char()
            if c == "}" then return obj end
        end
    end

    parse_value = function()
        skip_ws()
        local c = str:sub(pos, pos)
        if c == '"' then return parse_string()
        elseif c == '{' then return parse_object()
        elseif c == '[' then return parse_array()
        elseif c == 't' then pos = pos + 4; return true
        elseif c == 'f' then pos = pos + 5; return false
        elseif c == 'n' then pos = pos + 4; return nil
        else return parse_number()
        end
    end

    return parse_value()
end

--------------------------------------------------------------------------------
-- Утилиты файловой системы
--------------------------------------------------------------------------------
local function file_exists(path)
    local f = io.open(path, "r")
    if f then f:close(); return true end
    return false
end

local function read_file(path)
    local f = io.open(path, "r")
    if not f then return nil end
    local content = f:read("*a")
    f:close()
    return content
end

local function write_file(path, content)
    local f = io.open(path, "w")
    if not f then return false end
    f:write(content)
    f:close()
    return true
end

local function basename(path)
    return path:match("([^/\\]+)$") or path
end

local function dirname(path)
    return path:match("^(.*)[/\\]") or "."
end

local function join_path(...)
    local parts = {...}
    return table.concat(parts, package.config:sub(1,1) == "\\" and "\\" or "/")
end

local function mkdir_p(path)
    local sep = package.config:sub(1,1) == "\\" and "\\" or "/"
    if sep == "\\" then
        os.execute('mkdir "' .. path .. '" 2>nul')
    else
        os.execute('mkdir -p "' .. path .. '" 2>/dev/null')
    end
end

local function shell_exec(cmd)
    local handle = io.popen(cmd .. " 2>&1")
    if not handle then return "", -1 end
    local result = handle:read("*a")
    local ok, _, code = handle:close()
    return result or "", (code or (ok and 0 or 1))
end

local IS_WINDOWS = package.config:sub(1,1) == "\\"

--------------------------------------------------------------------------------
-- Таймкоды
--------------------------------------------------------------------------------
local function ms_to_timecode(ms)
    if ms < 0 then ms = 0 end
    local total_s = ms / 1000.0
    local h = math.floor(total_s / 3600)
    local m = math.floor((total_s % 3600) / 60)
    local s = math.floor(total_s % 60)
    local mil = math.floor(ms % 1000)
    return string.format("%02d:%02d:%02d,%03d", h, m, s, mil)
end

local function timecode_to_ms(tc)
    tc = tc:gsub(",", ".")
    local h, m, rest = tc:match("(%d+):(%d+):(.+)")
    if not h then return 0 end
    local s, mil = rest:match("(%d+)%.(%d+)")
    if not s then s = rest; mil = "0" end
    return (tonumber(h)*3600 + tonumber(m)*60 + tonumber(s))*1000 + tonumber(mil)
end

local function ms_to_frames(ms, fps)
    fps = fps or 25.0
    return math.floor(ms / 1000.0 * fps + 0.5)
end

local function frames_to_ms(frames, fps)
    fps = fps or 25.0
    return math.floor(frames / fps * 1000 + 0.5)
end

local function frames_to_resolve_tc(frames, fps)
    fps = fps or 25.0
    local fps_int = math.floor(fps + 0.5)
    local f = frames % fps_int
    local total_s = math.floor(frames / fps_int)
    local s = total_s % 60
    local total_m = math.floor(total_s / 60)
    local m = total_m % 60
    local h = math.floor(total_m / 60)
    return string.format("%02d:%02d:%02d:%02d", h, m, s, f)
end

local function resolve_tc_to_frames(tc, fps)
    fps = fps or 25.0
    local fps_int = math.floor(fps + 0.5)
    local h, m, s, f = tc:match("(%d+):(%d+):(%d+):(%d+)")
    if not h then return 0 end
    return (tonumber(h)*3600 + tonumber(m)*60 + tonumber(s)) * fps_int + tonumber(f)
end

--------------------------------------------------------------------------------
-- SRT парсер
--------------------------------------------------------------------------------
local function parse_srt(content)
    local blocks = {}
    for raw in (content .. "\n\n"):gmatch("(.-)%s*\n%s*\n") do
        raw = raw:match("^%s*(.-)%s*$")
        if raw and #raw > 0 then
            local lines = {}
            for line in raw:gmatch("([^\n]+)") do
                lines[#lines + 1] = line
            end
            if #lines >= 3 then
                local idx = tonumber(lines[1])
                if idx then
                    local tc1, tc2 = lines[2]:match("(%d%d:%d%d:%d%d[,.]%d%d%d)%s*%-%->%s*(%d%d:%d%d:%d%d[,.]%d%d%d)")
                    if tc1 then
                        local text_parts = {}
                        for i = 3, #lines do text_parts[#text_parts + 1] = lines[i] end
                        local text = table.concat(text_parts, "\n"):match("^%s*(.-)%s*$")
                        local deleted = text:find("%[DELETE%]") ~= nil
                        if deleted then
                            text = text:gsub("%[DELETE%]", ""):match("^%s*(.-)%s*$")
                        end
                        blocks[#blocks + 1] = {
                            index = idx,
                            start_ms = timecode_to_ms(tc1),
                            end_ms = timecode_to_ms(tc2),
                            text = text,
                            deleted = deleted,
                        }
                    end
                end
            end
        end
    end
    return blocks
end

local function read_srt(path)
    local content = read_file(path)
    if not content then return {} end
    return parse_srt(content)
end

local function write_srt(blocks, path)
    local parts = {}
    for i, b in ipairs(blocks) do
        local prefix = b.deleted and "[DELETE] " or ""
        parts[#parts + 1] = string.format("%d\n%s --> %s\n%s%s\n",
            i, ms_to_timecode(b.start_ms), ms_to_timecode(b.end_ms), prefix, b.text)
    end
    write_file(path, table.concat(parts, "\n"))
end

local function build_srt_chunk_text(blocks)
    local parts = {}
    for _, b in ipairs(blocks) do
        parts[#parts + 1] = string.format("%d\n%s --> %s\n%s\n",
            b.index, ms_to_timecode(b.start_ms), ms_to_timecode(b.end_ms), b.text)
    end
    return table.concat(parts, "\n")
end

local function merge_silence_and_ai(silence_regions, ai_blocks)
    local del = {}
    for _, r in ipairs(silence_regions) do del[#del + 1] = {r[1], r[2]} end
    for _, b in ipairs(ai_blocks) do
        if b.deleted then del[#del + 1] = {b.start_ms, b.end_ms} end
    end
    if #del == 0 then return {} end
    table.sort(del, function(a, b) return a[1] < b[1] end)
    local merged = { {del[1][1], del[1][2]} }
    for i = 2, #del do
        local last = merged[#merged]
        if del[i][1] <= last[2] then
            last[2] = math.max(last[2], del[i][2])
        else
            merged[#merged + 1] = {del[i][1], del[i][2]}
        end
    end
    return merged
end

local function invert_regions(delete_regions, total_ms)
    if #delete_regions == 0 then return {{0, total_ms}} end
    local sorted = {}
    for _, r in ipairs(delete_regions) do sorted[#sorted + 1] = {r[1], r[2]} end
    table.sort(sorted, function(a, b) return a[1] < b[1] end)
    local keep = {}
    local prev_end = 0
    for _, r in ipairs(sorted) do
        if r[1] > prev_end then keep[#keep + 1] = {prev_end, r[1]} end
        prev_end = math.max(prev_end, r[2])
    end
    if prev_end < total_ms then keep[#keep + 1] = {prev_end, total_ms} end
    return keep
end

local function chunk_blocks(blocks, size)
    size = size or 50
    local chunks = {}
    for i = 1, #blocks, size do
        local chunk = {}
        for j = i, math.min(i + size - 1, #blocks) do
            chunk[#chunk + 1] = blocks[j]
        end
        chunks[#chunks + 1] = chunk
    end
    return chunks
end

--------------------------------------------------------------------------------
-- Логгер
--------------------------------------------------------------------------------
local Logger = {}
Logger.__index = Logger

local _logger_instance = nil
local _ui_callback = nil

function Logger.new(working_dir)
    local self = setmetatable({}, Logger)
    self.working_dir = working_dir or ""
    self.log_file = nil
    if working_dir and working_dir ~= "" then
        local ts = os.date("%Y%m%d_%H%M%S")
        local path = join_path(working_dir, "autoeditor_" .. ts .. ".log")
        self.log_file = io.open(path, "a")
    end
    return self
end

function Logger:_write(level, msg)
    local ts = os.date("%H:%M:%S")
    local line = string.format("[%s] %-7s %s", ts, level, msg)
    print(line)
    if self.log_file then
        self.log_file:write(line .. "\n")
        self.log_file:flush()
    end
    if _ui_callback then
        pcall(_ui_callback, line)
    end
end

function Logger:info(msg) self:_write("INFO", msg) end
function Logger:warning(msg) self:_write("WARNING", msg) end
function Logger:error(msg) self:_write("ERROR", msg) end
function Logger:debug(msg) self:_write("DEBUG", msg) end

local function get_logger()
    if not _logger_instance then
        _logger_instance = Logger.new("")
    end
    return _logger_instance
end

local function setup_logger(working_dir)
    _logger_instance = Logger.new(working_dir)
    return _logger_instance
end

local function set_ui_callback(cb)
    _ui_callback = cb
end

--------------------------------------------------------------------------------
-- Конфигурация
--------------------------------------------------------------------------------
local CONFIG_FILE = join_path(PLUGIN_DIR, "autoeditor_config.json")

local CONFIG_DEFAULTS = {
    main_video_path = "",
    screencast_path = "",
    working_dir = "",
    transition_video_path = "",
    title_background_path = "",
    title_style = "default",
    openrouter_api_key = "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",
    openrouter_model = "google/gemini-2.0-flash-001",
    ai_chunk_size = 50,
    silence_threshold_db = -40,
    silence_min_duration_ms = 500,
    zoom_min = 1.0,
    zoom_max = 1.3,
    multicam_min_interval = 5,
    multicam_max_interval = 15,
    timeline_name = "AutoEditor_Final",
    fps = 25.0,
    subtitle_language = "Russian",
    step_statuses = {
        ["1_import"] = "pending",
        ["2_sync"] = "pending",
        ["3_silence"] = "pending",
        ["4_subtitles"] = "pending",
        ["5_ai_clean"] = "pending",
        ["6_cut"] = "pending",
        ["7_multicam"] = "pending",
        ["8_zoom"] = "pending",
        ["9_transitions"] = "pending",
        ["10_titles"] = "pending",
    },
}

local Config = {}
Config.__index = Config

function Config.new()
    local self = setmetatable({}, Config)
    self._data = {}
    self:load()
    return self
end

function Config:load()
    -- Копируем дефолты
    self._data = {}
    for k, v in pairs(CONFIG_DEFAULTS) do
        if type(v) == "table" then
            self._data[k] = {}
            for kk, vv in pairs(v) do self._data[k][kk] = vv end
        else
            self._data[k] = v
        end
    end
    -- Подмешиваем сохранённые
    local content = read_file(CONFIG_FILE)
    if content then
        local saved = json.decode(content)
        if saved then
            for k, v in pairs(saved) do
                if type(v) == "table" and type(self._data[k]) == "table" then
                    for kk, vv in pairs(v) do self._data[k][kk] = vv end
                else
                    self._data[k] = v
                end
            end
        end
    end
end

function Config:save()
    write_file(CONFIG_FILE, json.encode(self._data, true))
end

function Config:get(key, default)
    local v = self._data[key]
    if v == nil then return default end
    return v
end

function Config:set(key, value)
    self._data[key] = value
end

function Config:get_step_status(step_key)
    local s = self._data.step_statuses or {}
    return s[step_key] or "pending"
end

function Config:set_step_status(step_key, status)
    if not self._data.step_statuses then self._data.step_statuses = {} end
    self._data.step_statuses[step_key] = status
    self:save()
end

function Config:reset_steps()
    self._data.step_statuses = {}
    for k, v in pairs(CONFIG_DEFAULTS.step_statuses) do
        self._data.step_statuses[k] = v
    end
    self:save()
end

function Config:working_path(filename)
    return join_path(self:get("working_dir", ""), filename)
end

--------------------------------------------------------------------------------
-- Resolve API
--------------------------------------------------------------------------------
local _resolve = nil
local _project = nil

local function get_resolve()
    if _resolve then return _resolve end
    _resolve = resolve -- Resolve внедряет глобальную переменную при запуске из Scripts
    if not _resolve then
        error("Не удалось подключиться к DaVinci Resolve.\n"
            .. "Запустите этот скрипт из Resolve (Workspace > Scripts).")
    end
    return _resolve
end

local function get_project_manager()
    return get_resolve():GetProjectManager()
end

local function get_current_project()
    if not _project then
        _project = get_project_manager():GetCurrentProject()
    end
    return _project
end

local function get_media_pool()
    return get_current_project():GetMediaPool()
end

local function get_current_timeline()
    return get_current_project():GetCurrentTimeline()
end

local function get_fps()
    local tl = get_current_timeline()
    if tl then
        local setting = tl:GetSetting("timelineFrameRate")
        local n = tonumber(setting)
        if n and n > 0 then return n end
    end
    return 25.0
end

local function create_timeline(name)
    local log = get_logger()
    local mp = get_media_pool()
    local tl = mp:CreateEmptyTimeline(name)
    if tl then
        get_current_project():SetCurrentTimeline(tl)
        log:info("Таймлайн создан: " .. name)
    else
        log:error("Не удалось создать таймлайн: " .. name)
    end
    return tl
end

local function get_root_folder()
    return get_media_pool():GetRootFolder()
end

local function find_bin(name, parent)
    local mp = get_media_pool()
    if not parent then parent = get_root_folder() end
    for _, sub in ipairs(parent:GetSubFolderList()) do
        if sub:GetName() == name then return sub end
    end
    mp:SetCurrentFolder(parent)
    return mp:AddSubFolder(parent, name)
end

local function get_clip_duration_frames(clip)
    local props = clip:GetClipProperty()
    local dur = props and props["Duration"] or ""
    if dur == "" then return 0 end
    local parts = {}
    for p in dur:gmatch("[^:]+") do parts[#parts + 1] = p end
    if #parts == 4 then
        return resolve_tc_to_frames(dur, get_fps())
    end
    return 0
end

local function get_clip_duration_ms(clip)
    local frames = get_clip_duration_frames(clip)
    local fps = get_fps()
    return math.floor(frames / fps * 1000 + 0.5)
end

--------------------------------------------------------------------------------
-- Шаг 1: Импорт медиа
--------------------------------------------------------------------------------
local function import_media(main_video_path, screencast_path)
    local log = get_logger()
    local mp = get_media_pool()
    local result = {}

    if not main_video_path or main_video_path == "" or not file_exists(main_video_path) then
        error("Основное видео не найдено: " .. tostring(main_video_path))
    end

    local ae_bin = find_bin("AutoEditor")
    mp:SetCurrentFolder(ae_bin)

    log:info("Импорт основного видео: " .. basename(main_video_path))
    local clips = mp:ImportMedia({main_video_path})
    if not clips or #clips == 0 then
        error("Не удалось импортировать: " .. main_video_path)
    end
    local main_clip = clips[1]
    main_clip:SetClipProperty("Comments", "AutoEditor:main")
    result.main = main_clip
    log:info("Основное видео импортировано: " .. main_clip:GetName())

    if screencast_path and screencast_path ~= "" and file_exists(screencast_path) then
        log:info("Импорт скринкаста: " .. basename(screencast_path))
        local sc_clips = mp:ImportMedia({screencast_path})
        if sc_clips and #sc_clips > 0 then
            local sc_clip = sc_clips[1]
            sc_clip:SetClipProperty("Comments", "AutoEditor:screencast")
            result.screencast = sc_clip
            log:info("Скринкаст импортирован: " .. sc_clip:GetName())
        else
            log:warning("Не удалось импортировать скринкаст: " .. screencast_path)
        end
    end

    -- Создаём таймлайн и размещаем клипы: V1=основное видео, V2=скринкаст
    local project = get_current_project()
    local tl_name = "AutoEditor_Timeline"

    -- Проверяем, не существует ли уже такой таймлайн
    local existing_tl = nil
    local tl_count = project:GetTimelineCount()
    for idx = 1, tl_count do
        local t = project:GetTimelineByIndex(idx)
        if t and t:GetName() == tl_name then
            existing_tl = t
            break
        end
    end

    if existing_tl then
        project:SetCurrentTimeline(existing_tl)
        log:info("Таймлайн уже существует: " .. tl_name .. " (используется существующий)")
    else
        -- Создаём таймлайн с обоими клипами друг над другом (V1 + V2)
        local clip_infos = {
            { mediaPoolItem = main_clip, trackIndex = 1, mediaType = 1 },
        }
        if result.screencast then
            clip_infos[#clip_infos + 1] = {
                mediaPoolItem = result.screencast, trackIndex = 2, mediaType = 1,
            }
        end

        local tl = mp:CreateTimelineFromClips(tl_name, clip_infos)
        if tl then
            project:SetCurrentTimeline(tl)
            if result.screencast then
                log:info("Таймлайн создан: " .. tl_name .. " (V1=камера, V2=скринкаст, друг над другом)")
            else
                log:info("Таймлайн создан: " .. tl_name .. " (основной клип на V1)")
            end
        else
            -- Альтернативный способ: пустой таймлайн + добавление по одному
            log:info("Пробуем альтернативный способ создания таймлайна...")
            tl = mp:CreateEmptyTimeline(tl_name)
            if tl then
                project:SetCurrentTimeline(tl)
                local appended = mp:AppendToTimeline({main_clip})
                if appended then
                    log:info("Основной клип добавлен на V1")
                end
                if result.screencast then
                    if tl:GetTrackCount("video") < 2 then
                        tl:AddTrack("video")
                    end
                    local sc_ok = mp:AppendToTimeline({
                        { mediaPoolItem = result.screencast, trackIndex = 2, mediaType = 1 },
                    })
                    if sc_ok then
                        log:info("Скринкаст добавлен на V2")
                    else
                        log:warning("Не удалось добавить скринкаст на V2")
                    end
                end
            else
                log:warning("Не удалось создать таймлайн автоматически")
            end
        end
        -- Аудио V2 НЕ отключаем — оно нужно для синхронизации (шаг 2)
        if result.screencast then
            log:info("Аудио V2 оставлено включённым для синхронизации (шаг 2)")
        end
    end

    log:info("Шаг 1 завершён: импортировано клипов: " .. (result.screencast and 2 or 1))
    return result
end

local function _search_folder(folder, result)
    for _, clip in ipairs(folder:GetClipList()) do
        local comments = clip:GetClipProperty("Comments") or ""
        if comments:find("AutoEditor:main") then result.main = clip
        elseif comments:find("AutoEditor:screencast") then result.screencast = clip end
    end
    for _, sub in ipairs(folder:GetSubFolderList()) do
        _search_folder(sub, result)
    end
end

local function find_tagged_clips()
    local result = {}
    _search_folder(get_root_folder(), result)
    return result
end

--------------------------------------------------------------------------------
-- Шаг 2: Синхронизация аудио по звуковой волне (ffmpeg)
--------------------------------------------------------------------------------

--- Найти момент первого звука в файле через silencedetect.
--- @return число секунд до первого звука
local function detect_first_sound(file_path, threshold_db)
    local log = get_logger()
    threshold_db = threshold_db or -30
    log:info("  Путь к файлу: " .. tostring(file_path))
    if not file_exists(file_path) then
        log:warning("  Файл не найден: " .. tostring(file_path))
        return 0.0
    end
    local cmd = string.format(
        'ffmpeg -i "%s" -af "silencedetect=n=%ddB:d=0.1" -t 120 -f null -',
        file_path, threshold_db)
    local output, code = shell_exec(cmd)
    if code ~= 0 and (not output or output == "") then
        log:warning("  ffmpeg не удалось выполнить (код " .. tostring(code) .. ")")
        return 0.0
    end
    -- silence_end — момент, когда тишина закончилась (= начало звука)
    local first = output:match("silence_end:%s*([%d%.]+)")
    if first then return tonumber(first) end
    -- Если silence_end не найден — проверяем, был ли вообще анализ
    if not output:match("silencedetect") then
        log:warning("  ffmpeg: silencedetect не запустился — возможно файл повреждён")
    end
    return 0.0 -- если тишины нет — звук с самого начала
end

local function auto_sync_audio(clips_dict, config)
    local log = get_logger()
    local main_clip = clips_dict.main
    local screencast_clip = clips_dict.screencast

    if not main_clip then error("Основной клип для синхронизации аудио не найден") end
    if not screencast_clip then
        log:info("Скринкаст отсутствует — пропуск синхронизации аудио")
        return 0
    end

    log:info("Синхронизация аудио по звуковой волне...")
    log:info("  Основной: " .. main_clip:GetName())
    log:info("  Скринкаст: " .. screencast_clip:GetName())

    -- Получаем пути к файлам
    local main_path = main_clip:GetClipProperty("File Path") or ""
    local sc_path = screencast_clip:GetClipProperty("File Path") or ""

    if main_path == "" or sc_path == "" then
        log:warning("Не удалось получить пути к файлам — пропуск синхронизации")
        return 0
    end

    -- Находим момент первого звука в каждом файле
    log:info("Анализ звуковой волны основного видео...")
    local main_onset = detect_first_sound(main_path)
    log:info(string.format("  Первый звук (основное): %.3f с", main_onset))

    log:info("Анализ звуковой волны скринкаста...")
    local sc_onset = detect_first_sound(sc_path)
    log:info(string.format("  Первый звук (скринкаст): %.3f с", sc_onset))

    -- Смещение: положительное = скринкаст начал запись раньше
    local offset_sec = sc_onset - main_onset
    local offset_ms = math.floor(offset_sec * 1000 + 0.5)

    log:info(string.format("Смещение аудио: %.3f с (%d мс)", offset_sec, offset_ms))

    if math.abs(offset_ms) < 50 then
        log:info("Смещение минимальное — клипы уже синхронизированы")
        offset_ms = 0
    end

    -- Нормализация громкости обоих клипов (выравнивание уровней)
    log:info("Нормализация уровней звука...")
    local tmp_main = os.tmpname() .. ".wav"
    local tmp_sc = os.tmpname() .. ".wav"

    shell_exec(string.format(
        'ffmpeg -y -i "%s" -af "loudnorm=I=-16:TP=-1.5:LRA=11" -ar 48000 -ac 2 "%s"',
        main_path, tmp_main))
    shell_exec(string.format(
        'ffmpeg -y -i "%s" -af "loudnorm=I=-16:TP=-1.5:LRA=11" -ar 48000 -ac 2 "%s"',
        sc_path, tmp_sc))

    -- Проверяем, получилось ли нормализовать
    if file_exists(tmp_main) then
        log:info("  Основное видео: уровень нормализован до -16 LUFS")
    end
    if file_exists(tmp_sc) then
        log:info("  Скринкаст: уровень нормализован до -16 LUFS")
    end

    os.remove(tmp_main)
    os.remove(tmp_sc)

    -- Сохраняем смещение в конфиг для шага 7 (мультикамера)
    if config then
        config:set("audio_offset_ms", offset_ms)
        config:save()
    end

    -- Сохраняем в JSON для справки
    local working_dir = config and config:get("working_dir", "") or ""
    if working_dir ~= "" then
        local data = {
            main_onset_sec = main_onset,
            screencast_onset_sec = sc_onset,
            offset_ms = offset_ms,
            offset_sec = offset_sec,
        }
        write_file(join_path(working_dir, "audio_sync.json"), json.encode(data, true))
        log:info("Данные синхронизации сохранены в audio_sync.json")
    end

    -- После синхронизации отключаем аудио V2 (используется аудио основного видео)
    local timeline = get_current_timeline()
    if timeline and timeline:GetTrackCount("audio") >= 2 then
        timeline:SetTrackEnable("audio", 2, false)
        log:info("Аудио V2 отключено после синхронизации")
    end

    log:info(string.format("Шаг 2 завершён: смещение %d мс будет применено при мультикамере", offset_ms))
    return offset_ms
end

--------------------------------------------------------------------------------
-- Шаг 3: Обнаружение тишины (ffmpeg silencedetect)
--------------------------------------------------------------------------------
local function auto_detect_threshold(video_path)
    local log = get_logger()
    log:info("Автоопределение порога тишины...")

    if not file_exists(video_path) then
        log:warning("  Файл не найден: " .. tostring(video_path))
        return -40
    end

    local cmd = string.format('ffmpeg -i "%s" -af "volumedetect" -f null -', video_path)
    local output = shell_exec(cmd)

    local mean_vol = output:match("mean_volume:%s*([-%.%d]+)%s*dB")
    if mean_vol then
        mean_vol = tonumber(mean_vol)
        local threshold = math.floor(mean_vol + 3 + 0.5)
        log:info(string.format("  Средняя громкость: %.1f дБ → порог: %d дБ", mean_vol, threshold))
        return threshold
    end

    log:warning("  Не удалось определить громкость — используется -40 дБ")
    return -40
end

local function detect_silence(video_path, threshold_db, min_duration_ms, working_dir)
    local log = get_logger()
    threshold_db = threshold_db or -40
    min_duration_ms = min_duration_ms or 500

    log:info("Обнаружение тишины в: " .. basename(video_path))
    log:info("  Полный путь: " .. tostring(video_path))
    log:info(string.format("  Порог: %d дБ, мин. длительность: %d мс", threshold_db, min_duration_ms))

    if not file_exists(video_path) then
        log:error("  Файл не найден: " .. tostring(video_path))
        return {}
    end

    local min_dur_sec = min_duration_ms / 1000.0
    local cmd = string.format(
        'ffmpeg -i "%s" -af "silencedetect=n=%ddB:d=%.3f" -f null -',
        video_path, threshold_db, min_dur_sec
    )

    log:info("Извлечение и анализ аудио через ffmpeg...")
    local output, code = shell_exec(cmd)

    if not output or output == "" then
        log:error("  ffmpeg не вернул вывод (код " .. tostring(code) .. "). Проверьте, что ffmpeg установлен и доступен.")
        return {}
    end

    -- Определяем общую длительность
    local total_duration_ms = 0
    local dur_str = output:match("Duration:%s*(%d+:%d+:%d+%.%d+)")
    if dur_str then
        local h, m, s = dur_str:match("(%d+):(%d+):([%d%.]+)")
        if h then total_duration_ms = math.floor((tonumber(h)*3600 + tonumber(m)*60 + tonumber(s)) * 1000) end
    end

    -- Парсим silence_start / silence_end
    local regions = {}
    local starts = {}
    for ts in output:gmatch("silence_start:%s*([%d%.]+)") do
        starts[#starts + 1] = math.floor(tonumber(ts) * 1000)
    end
    local ends = {}
    for te in output:gmatch("silence_end:%s*([%d%.]+)") do
        ends[#ends + 1] = math.floor(tonumber(te) * 1000)
    end
    for i = 1, math.min(#starts, #ends) do
        regions[#regions + 1] = {starts[i], ends[i]}
    end

    log:info(string.format("Найдено участков тишины: %d (длительность аудио: %.1fс)",
        #regions, total_duration_ms / 1000.0))

    local total_silence = 0
    for _, r in ipairs(regions) do total_silence = total_silence + (r[2] - r[1]) end
    if total_duration_ms > 0 then
        log:info(string.format("Общая тишина: %.1fс (%.1f%%)",
            total_silence / 1000.0, total_silence / total_duration_ms * 100))
    end

    -- Сохраняем в JSON
    if working_dir and working_dir ~= "" then
        local data = {
            video = video_path,
            threshold_db = threshold_db,
            min_duration_ms = min_duration_ms,
            total_duration_ms = total_duration_ms,
            regions = regions,
        }
        write_file(join_path(working_dir, "silence_regions.json"), json.encode(data, true))
        log:info("Участки тишины сохранены")
    end

    return regions
end

local function load_silence_regions(working_dir)
    local path = join_path(working_dir, "silence_regions.json")
    local content = read_file(path)
    if not content then return {} end
    local data = json.decode(content)
    if not data or not data.regions then return {} end
    return data.regions
end

--------------------------------------------------------------------------------
-- Шаг 4: Генерация субтитров
--------------------------------------------------------------------------------
local function generate_subtitles(language)
    local log = get_logger()
    local timeline = get_current_timeline()
    if not timeline then error("Нет активного таймлайна для генерации субтитров") end

    language = language or "Russian"
    log:info("Генерация субтитров (язык: " .. language .. ")...")
    log:info("Это может занять несколько минут в зависимости от длины видео.")

    local result = timeline:CreateSubtitlesFromAudio({language = language, format = "SRT"})
    if not result then
        log:warning("CreateSubtitlesFromAudio не вернул результат. Убедитесь, что используется Resolve Studio.")
        return nil
    end
    log:info("Генерация субтитров завершена")
    return result
end

local function export_subtitles(working_dir, filename)
    local log = get_logger()
    local timeline = get_current_timeline()
    if not timeline then error("Нет активного таймлайна") end

    filename = filename or "original.srt"
    local output_path = join_path(working_dir, filename)

    local result = timeline:ExportSubtitles(output_path, "SRT")
    if not result then
        log:warning("ExportSubtitles не удался, попытка ручного извлечения...")
        -- Ручное извлечение
        local sub_count = timeline:GetTrackCount("subtitle")
        if sub_count == 0 then error("В таймлайне не найдены дорожки субтитров") end
        local items = timeline:GetItemListInTrack("subtitle", 1)
        if not items or #items == 0 then error("В дорожке не найдены элементы субтитров") end

        local fps = get_fps()
        local f = io.open(output_path, "w")
        for i, item in ipairs(items) do
            local start_frame = item:GetStart()
            local end_frame = item:GetEnd()
            local text = item:GetName() or ""
            local start_ms = math.floor(start_frame / fps * 1000 + 0.5)
            local end_ms = math.floor(end_frame / fps * 1000 + 0.5)
            f:write(string.format("%d\n%s --> %s\n%s\n\n",
                i, ms_to_timecode(start_ms), ms_to_timecode(end_ms), text))
        end
        f:close()
        log:info("Вручную извлечено " .. #items .. " блоков субтитров")
    else
        log:info("Субтитры экспортированы в: " .. output_path)
    end

    if file_exists(output_path) then
        local blocks = read_srt(output_path)
        log:info("Экспортировано " .. #blocks .. " блоков субтитров")
        return output_path
    else
        error("Не удалось экспортировать субтитры")
    end
end

local function import_srt_to_timeline(srt_path)
    local log = get_logger()
    local timeline = get_current_timeline()
    if not timeline then error("Нет активного таймлайна") end
    if not file_exists(srt_path) then error("SRT-файл не найден: " .. srt_path) end
    local result = timeline:ImportSubtitles(srt_path)
    if result then log:info("Субтитры импортированы из: " .. srt_path)
    else log:warning("ImportSubtitles не вернул результат") end
    return result
end

--------------------------------------------------------------------------------
-- Шаг 5: Очистка ИИ (curl → OpenRouter)
--------------------------------------------------------------------------------
local OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

local AI_SYSTEM_PROMPT = [[Ты — редактор видео. Тебе дают блоки субтитров из русскоязычного видео.

Твоя задача: пометить для удаления блоки, которые содержат:
- Слова-паразиты, мычание, "ээ", "ммм", "ну", "вот", повторы
- Незаконченные фразы, оговорки, самоисправления
- Паузы и бессмысленные фрагменты
- Технический мусор (кашель, вздохи)

ВАЖНО:
- Перед текстом удаляемого блока поставь маркер [DELETE]
- НЕ МЕНЯЙ таймкоды — они должны остаться точно такими же
- НЕ МЕНЯЙ текст (кроме добавления [DELETE])
- НЕ УДАЛЯЙ блоки с осмысленным содержанием
- Сохрани нумерацию блоков без изменений
- Верни ВСЕ блоки (и помеченные, и непомеченные)

Формат вывода — стандартный SRT с маркером [DELETE] перед текстом удаляемых блоков.]]

local function process_chunk_ai(blocks, api_key, model)
    local log = get_logger()
    model = model or "google/gemini-2.0-flash-001"
    local srt_text = build_srt_chunk_text(blocks)

    log:info(string.format("Отправка %d блоков в ИИ (%s)...", #blocks, model))

    -- Формируем JSON payload
    local payload = json.encode({
        model = model,
        messages = {
            {role = "system", content = AI_SYSTEM_PROMPT},
            {role = "user", content = srt_text},
        },
        temperature = 0.1,
        max_tokens = 16000,
    })

    -- Записываем payload во временный файл (чтобы избежать проблем с экранированием)
    local tmp_payload = os.tmpname()
    write_file(tmp_payload, payload)

    local cmd = string.format(
        'curl -s -X POST "%s" -H "Authorization: Bearer %s" -H "Content-Type: application/json" -d @"%s"',
        OPENROUTER_URL, api_key, tmp_payload
    )

    local response_text, code = shell_exec(cmd)
    os.remove(tmp_payload)

    if code ~= 0 then
        error("Ошибка curl: код " .. tostring(code))
    end

    local data = json.decode(response_text)
    if not data or not data.choices or #data.choices == 0 then
        error("Пустой ответ от API: " .. (response_text:sub(1, 200) or ""))
    end

    local content = data.choices[1].message.content
    local delete_count = 0
    for _ in content:gmatch("%[DELETE%]") do delete_count = delete_count + 1 end
    log:info(string.format("ИИ пометил %d/%d блоков на удаление", delete_count, #blocks))

    return content
end

local function run_ai_cleanup(srt_path, output_path, api_key, model, chunk_size)
    local log = get_logger()
    chunk_size = chunk_size or 50

    local blocks = read_srt(srt_path)
    log:info("Загружено " .. #blocks .. " блоков субтитров из " .. srt_path)

    local chunks = chunk_blocks(blocks, chunk_size)
    log:info(string.format("Разбито на %d частей по %d блоков", #chunks, chunk_size))

    local all_cleaned = {}
    for i, chunk in ipairs(chunks) do
        log:info(string.format("Обработка части %d/%d...", i, #chunks))
        local ok, result = pcall(process_chunk_ai, chunk, api_key, model)
        if ok then
            all_cleaned[#all_cleaned + 1] = result
        else
            log:error("Ошибка при обработке части " .. i .. ": " .. tostring(result))
            all_cleaned[#all_cleaned + 1] = build_srt_chunk_text(chunk)
        end
    end

    local merged_text = table.concat(all_cleaned, "\n\n")
    local cleaned_blocks = parse_srt(merged_text)

    local deleted = 0
    for _, b in ipairs(cleaned_blocks) do if b.deleted then deleted = deleted + 1 end end
    log:info(string.format("Очистка ИИ завершена: %d/%d блоков помечено на удаление",
        deleted, #cleaned_blocks))

    write_srt(cleaned_blocks, output_path)
    log:info("Очищенные субтитры сохранены в: " .. output_path)
    return cleaned_blocks
end

--------------------------------------------------------------------------------
-- Шаг 4: Нарезка тишины (только по регионам тишины, без ИИ)
--------------------------------------------------------------------------------
local function compute_silence_keep_segments(working_dir, total_duration_ms, fps)
    local log = get_logger()
    fps = fps or 25.0

    local silence_regions = load_silence_regions(working_dir)
    log:info("Загружено " .. #silence_regions .. " регионов тишины")

    local keep_segments = invert_regions(silence_regions, total_duration_ms)
    log:info("Сегментов для сохранения: " .. #keep_segments)

    local kept_ms = 0
    for _, seg in ipairs(keep_segments) do kept_ms = kept_ms + (seg[2] - seg[1]) end
    local removed_ms = total_duration_ms - kept_ms
    log:info(string.format("Сохраняется %.1fс, удаляется %.1fс тишины (%.1f%% вырезано)",
        kept_ms / 1000, removed_ms / 1000,
        total_duration_ms > 0 and (removed_ms / total_duration_ms * 100) or 0))

    local data = {
        total_duration_ms = total_duration_ms,
        kept_ms = kept_ms, removed_ms = removed_ms,
        segments = keep_segments,
    }
    write_file(join_path(working_dir, "keep_segments_silence.json"), json.encode(data, true))
    return keep_segments
end

--------------------------------------------------------------------------------
-- Шаг 7: Нарезка мусора (ИИ-удаления на чистом таймлайне)
--------------------------------------------------------------------------------

--- Маппинг времени с чистого таймлайна на оригинальное видео.
--- @param t_clean_ms число — позиция на чистом таймлайне (мс)
--- @param keep_segments таблица — сегменты тишины (оригинальное время)
--- @return число — позиция в оригинальном видео (мс)
local function clean_to_original(t_clean_ms, keep_segments)
    local elapsed = 0
    for _, seg in ipairs(keep_segments) do
        local seg_dur = seg[2] - seg[1]
        if elapsed + seg_dur >= t_clean_ms then
            return seg[1] + (t_clean_ms - elapsed)
        end
        elapsed = elapsed + seg_dur
    end
    -- За пределами — вернуть конец последнего сегмента
    if #keep_segments > 0 then return keep_segments[#keep_segments][2] end
    return t_clean_ms
end

local function compute_ai_keep_segments(working_dir, total_duration_ms, fps)
    local log = get_logger()
    fps = fps or 25.0

    -- Загружаем keep-сегменты от нарезки тишины (шаг 4)
    local silence_keep_path = join_path(working_dir, "keep_segments_silence.json")
    local silence_keep = {}
    if file_exists(silence_keep_path) then
        local content = read_file(silence_keep_path)
        local data = json.decode(content)
        if data and data.segments then silence_keep = data.segments end
    end
    log:info("Загружено " .. #silence_keep .. " сегментов после нарезки тишины")

    -- Загружаем ИИ-очищенные субтитры
    local cleaned_srt_path = join_path(working_dir, "cleaned.srt")
    if not file_exists(cleaned_srt_path) then
        log:warning("Файл cleaned.srt не найден — используются сегменты тишины без изменений")
        -- Копируем silence keep как финальные
        local content = read_file(silence_keep_path)
        if content then write_file(join_path(working_dir, "keep_segments.json"), content) end
        return silence_keep
    end

    local ai_blocks = read_srt(cleaned_srt_path)
    local deleted_count = 0
    for _, b in ipairs(ai_blocks) do if b.deleted then deleted_count = deleted_count + 1 end end
    log:info(string.format("ИИ пометил %d/%d блоков на удаление", deleted_count, #ai_blocks))

    -- Маппим ИИ-удаления с чистого таймлайна на оригинальное время
    local ai_delete_regions = {}
    for _, b in ipairs(ai_blocks) do
        if b.deleted then
            local orig_start = clean_to_original(b.start_ms, silence_keep)
            local orig_end = clean_to_original(b.end_ms, silence_keep)
            ai_delete_regions[#ai_delete_regions + 1] = {orig_start, orig_end}
        end
    end
    log:info("ИИ-удалений (в оригинальном времени): " .. #ai_delete_regions)

    -- Объединяем тишину + ИИ-удаления
    local silence_regions = load_silence_regions(working_dir)
    local all_delete = {}
    for _, r in ipairs(silence_regions) do all_delete[#all_delete + 1] = r end
    for _, r in ipairs(ai_delete_regions) do all_delete[#all_delete + 1] = r end

    -- Сортируем и объединяем пересечения
    table.sort(all_delete, function(a, b) return a[1] < b[1] end)
    local merged = {}
    for _, r in ipairs(all_delete) do
        if #merged == 0 or r[1] > merged[#merged][2] then
            merged[#merged + 1] = {r[1], r[2]}
        else
            merged[#merged][2] = math.max(merged[#merged][2], r[2])
        end
    end

    local keep_segments = invert_regions(merged, total_duration_ms)
    log:info("Финальных сегментов для сохранения: " .. #keep_segments)

    local kept_ms = 0
    for _, seg in ipairs(keep_segments) do kept_ms = kept_ms + (seg[2] - seg[1]) end
    local removed_ms = total_duration_ms - kept_ms
    log:info(string.format("Итого: сохраняется %.1fс, удаляется %.1fс (%.1f%% вырезано)",
        kept_ms / 1000, removed_ms / 1000,
        total_duration_ms > 0 and (removed_ms / total_duration_ms * 100) or 0))

    local data = {
        total_duration_ms = total_duration_ms,
        kept_ms = kept_ms, removed_ms = removed_ms,
        segments = keep_segments,
    }
    write_file(join_path(working_dir, "keep_segments.json"), json.encode(data, true))
    return keep_segments
end

local function rebuild_timeline(main_clip, keep_segments, timeline_name, fps, screencast_clip, audio_offset_ms)
    local log = get_logger()
    local mp = get_media_pool()
    fps = fps or 25.0
    audio_offset_ms = audio_offset_ms or 0

    log:info(string.format("Пересборка таймлайна '%s' из %d сегментов...",
        timeline_name, #keep_segments))

    local new_tl = create_timeline(timeline_name)
    if not new_tl then error("Не удалось создать таймлайн: " .. timeline_name) end

    -- V1: основное видео — все сохраняемые сегменты
    local clip_infos = {}
    for _, seg in ipairs(keep_segments) do
        clip_infos[#clip_infos + 1] = {
            mediaPoolItem = main_clip,
            startFrame = ms_to_frames(seg[1], fps),
            endFrame = ms_to_frames(seg[2], fps),
            trackIndex = 1,
            mediaType = 1,
        }
    end

    local result = mp:AppendToTimeline(clip_infos)
    if result then
        log:info("Добавлено " .. #clip_infos .. " сегментов основного видео на V1")
    else
        error("Не удалось добавить сегменты в таймлайн")
    end

    -- V2: скринкаст — те же сегменты со смещением аудио (blade+ripple на обеих дорожках)
    if screencast_clip then
        log:info("Добавление скринкаста на V2 (те же сегменты со смещением)...")
        if new_tl:GetTrackCount("video") < 2 then
            new_tl:AddTrack("video")
        end

        local sc_infos = {}
        for _, seg in ipairs(keep_segments) do
            local src_start_ms = math.max(0, seg[1] + audio_offset_ms)
            local src_end_ms = math.max(0, seg[2] + audio_offset_ms)
            sc_infos[#sc_infos + 1] = {
                mediaPoolItem = screencast_clip,
                startFrame = ms_to_frames(src_start_ms, fps),
                endFrame = ms_to_frames(src_end_ms, fps),
                trackIndex = 2,
                mediaType = 1,
            }
        end

        local sc_result = mp:AppendToTimeline(sc_infos)
        if sc_result then
            log:info("Добавлено " .. #sc_infos .. " сегментов скринкаста на V2")
            -- Отключаем аудио на V2
            new_tl:SetTrackEnable("audio", 2, false)
            log:info("Аудио на V2 отключено")
        else
            log:warning("Не удалось добавить сегменты скринкаста на V2")
        end
    end

    local items = new_tl:GetItemListInTrack("video", 1)
    local total_frames = 0
    if items then
        for _, item in ipairs(items) do total_frames = total_frames + item:GetDuration() end
    end
    log:info("Всего кадров в новом таймлайне: " .. total_frames)
    return new_tl
end

local function load_keep_segments(working_dir)
    local content = read_file(join_path(working_dir, "keep_segments.json"))
    if not content then return {} end
    local data = json.decode(content)
    if not data or not data.segments then return {} end
    return data.segments
end

local function auto_switch_intervals(keep_segments)
    local log = get_logger()
    if not keep_segments or #keep_segments == 0 then
        log:info("Нет сегментов — используются интервалы по умолчанию (5-15с)")
        return 5, 15
    end
    local total_dur = 0
    for _, seg in ipairs(keep_segments) do
        total_dur = total_dur + (seg[2] - seg[1]) / 1000.0
    end
    local avg_dur = total_dur / #keep_segments
    local min_iv = math.max(3, math.floor(avg_dur / 4 + 0.5))
    local max_iv = math.max(min_iv + 1, math.floor(avg_dur / 2 + 0.5))
    max_iv = math.min(max_iv, 30)
    log:info(string.format("Автоинтервалы переключения: %d-%dс (средний сегмент: %.1fс)",
        min_iv, max_iv, avg_dur))
    return min_iv, max_iv
end

--------------------------------------------------------------------------------
-- Шаг 7: Мультикамера
-- V2 уже содержит все сегменты скринкаста (добавлены на шаге 6).
-- Мультикамера удаляет V2-клипы, где должна быть основная камера,
-- оставляя только интервалы переключения на скринкаст.
--------------------------------------------------------------------------------
local function distribute_multicam(screencast_clip, keep_segments, min_sec, max_sec, fps, audio_offset_ms)
    local log = get_logger()
    local mp = get_media_pool()
    local timeline = get_current_timeline()
    if not timeline then error("Нет активного таймлайна для мультикамерного распределения") end

    min_sec = min_sec or 5; max_sec = max_sec or 15; fps = fps or 25.0
    if not screencast_clip then
        log:info("Клип скринкаста отсутствует — пропускаем мультикамерное распределение")
        return 0
    end

    audio_offset_ms = audio_offset_ms or 0
    log:info("Вычисление точек переключения мультикамеры...")
    if audio_offset_ms ~= 0 then
        log:info(string.format("  Применяется смещение аудио: %d мс", audio_offset_ms))
    end
    math.randomseed(os.time())

    local timeline_pos_ms = 0
    local switch_regions = {}  -- интервалы, где показываем скринкаст
    local show_screencast = false

    for _, seg in ipairs(keep_segments) do
        local seg_dur = seg[2] - seg[1]
        local seg_offset = 0
        while seg_offset < seg_dur do
            local interval = math.random(min_sec, max_sec) * 1000
            local chunk_end = math.min(seg_offset + interval, seg_dur)
            if show_screencast then
                switch_regions[#switch_regions + 1] = {
                    timeline_pos_ms + seg_offset,
                    timeline_pos_ms + chunk_end,
                    seg[1] + seg_offset,
                }
            end
            show_screencast = not show_screencast
            seg_offset = chunk_end
        end
        timeline_pos_ms = timeline_pos_ms + seg_dur
    end

    log:info("Мультикамера: " .. #switch_regions .. " интервалов скринкаста")

    -- Удаляем все существующие клипы с V2 (размещены на шаге 6)
    if timeline:GetTrackCount("video") >= 2 then
        local v2_items = timeline:GetItemListInTrack("video", 2)
        if v2_items and #v2_items > 0 then
            for _, item in ipairs(v2_items) do
                timeline:DeleteTimelineItem(item)
            end
            log:info("Удалено " .. #v2_items .. " клипов с V2 для пересборки мультикамеры")
        end
    else
        timeline:AddTrack("video")
        log:info("Добавлена видеодорожка V2")
    end

    -- Размещаем только выбранные интервалы скринкаста на V2
    local clip_infos = {}
    for _, r in ipairs(switch_regions) do
        local src_start = ms_to_frames(math.max(0, r[3] + audio_offset_ms), fps)
        local dur_frames = ms_to_frames(r[2] - r[1], fps)
        clip_infos[#clip_infos + 1] = {
            mediaPoolItem = screencast_clip,
            startFrame = src_start,
            endFrame = src_start + dur_frames,
            trackIndex = 2,
            mediaType = 1,
        }
    end

    if #clip_infos > 0 then
        local result = mp:AppendToTimeline(clip_infos)
        if result then
            log:info("Размещено " .. #clip_infos .. " сегментов скринкаста на V2")
        else
            log:error("Не удалось разместить сегменты скринкаста на V2")
            return 0
        end
    end

    timeline:SetTrackEnable("audio", 2, false)
    log:info("Аудио на дорожке V2 отключено")
    return #clip_infos
end

--------------------------------------------------------------------------------
-- Шаг 8: Динамический зум
--------------------------------------------------------------------------------
local function apply_dynamic_zoom(zoom_min, zoom_max)
    local log = get_logger()
    local timeline = get_current_timeline()
    if not timeline then error("Нет активного таймлайна для анимации масштабирования") end

    zoom_min = zoom_min or 1.0; zoom_max = zoom_max or 1.3
    local items = timeline:GetItemListInTrack("video", 1)
    if not items or #items == 0 then log:warning("Клипы на V1 не найдены"); return 0 end

    log:info(string.format("Применение динамического масштабирования к %d клипам на V1...", #items))
    log:info(string.format("Диапазон масштабирования: %.2fx — %.2fx", zoom_min, zoom_max))

    math.randomseed(os.time())
    local count = 0
    for i, item in ipairs(items) do
        local zoom = zoom_min + math.random() * (zoom_max - zoom_min)
        zoom = math.floor(zoom * 1000 + 0.5) / 1000

        local sx = item:SetProperty("ZoomX", zoom)
        local sy = item:SetProperty("ZoomY", zoom)
        if sx and sy then
            count = count + 1
        else
            pcall(function()
                item:SetProperty("Pan", 0)
                item:SetProperty("Tilt", 0)
                item:SetProperty("ZoomX", zoom)
                item:SetProperty("ZoomY", zoom)
                count = count + 1
            end)
        end
    end

    log:info(string.format("Масштабирование применено к %d/%d клипам", count, #items))
    return count
end

--------------------------------------------------------------------------------
-- Шаг 9: Видеопереходы
--------------------------------------------------------------------------------
local COMPOSITE_ADD = 5

local function import_transition_video(transition_path)
    local log = get_logger()
    local mp = get_media_pool()
    if not transition_path or transition_path == "" or not file_exists(transition_path) then
        error("Видео перехода не найдено: " .. tostring(transition_path))
    end
    local ae_bin = find_bin("AutoEditor")
    local tr_bin = find_bin("Transitions", ae_bin)
    mp:SetCurrentFolder(tr_bin)
    local clips = mp:ImportMedia({transition_path})
    if not clips or #clips == 0 then error("Не удалось импортировать переход: " .. transition_path) end
    log:info("Видео перехода импортировано: " .. clips[1]:GetName())
    return clips[1]
end

local function apply_transitions(transition_clip, fps)
    local log = get_logger()
    local mp = get_media_pool()
    local timeline = get_current_timeline()
    if not timeline then error("Нет активного таймлайна для переходов") end

    fps = fps or 25.0
    local v1_items = timeline:GetItemListInTrack("video", 1)
    if not v1_items or #v1_items < 2 then
        log:info("Менее 2 клипов на V1 — нет точек склейки для переходов")
        return 0
    end

    local tr_dur = get_clip_duration_frames(transition_clip)
    local tr_half = math.floor(tr_dur / 2)
    log:info(string.format("Клип перехода: %s, длительность: %d кадров",
        transition_clip:GetName(), tr_dur))

    while timeline:GetTrackCount("video") < 3 do timeline:AddTrack("video") end
    log:info("Дорожка V3 готова для переходов")

    local cut_points = {}
    for i = 1, #v1_items - 1 do
        cut_points[#cut_points + 1] = v1_items[i]:GetEnd()
    end
    log:info("Найдено " .. #cut_points .. " точек склейки")

    local clip_infos = {}
    for _, cf in ipairs(cut_points) do
        clip_infos[#clip_infos + 1] = {
            mediaPoolItem = transition_clip,
            startFrame = 0, endFrame = tr_dur,
            trackIndex = 3,
            recordFrame = math.max(0, cf - tr_half),
            mediaType = 1,
        }
    end

    local result = mp:AppendToTimeline(clip_infos)
    if not result then log:error("Не удалось разместить клипы переходов на V3"); return 0 end

    local v3_items = timeline:GetItemListInTrack("video", 3)
    if v3_items then
        for _, item in ipairs(v3_items) do
            item:SetProperty("CompositeMode", COMPOSITE_ADD)
            item:SetProperty("Opacity", 80.0)
        end
        log:info("Режим наложения Add применён к " .. #v3_items .. " клипам переходов на V3")
    end

    timeline:SetTrackEnable("audio", 3, false)
    log:info("Шаг 9 завершён: размещено " .. #cut_points .. " переходов")
    return #cut_points
end

--------------------------------------------------------------------------------
-- Шаг 10: Титульные карточки
--------------------------------------------------------------------------------
local ASSETS_DIR = join_path(PLUGIN_DIR, "assets")
local STYLES_FILE = join_path(ASSETS_DIR, "titles", "styles.json")

local DEFAULT_STYLE = {
    font = "Arial", fontsize = 72, fontcolor = "white",
    borderw = 3, bordercolor = "black", duration_sec = 3,
    width = 1920, height = 1080, bg_color = "black",
}

local function load_style(style_name)
    style_name = style_name or "default"
    local content = read_file(STYLES_FILE)
    if content then
        local ok, styles = pcall(json.decode, content)
        if ok and styles and styles[style_name] then
            local merged = {}
            for k, v in pairs(DEFAULT_STYLE) do merged[k] = v end
            for k, v in pairs(styles[style_name]) do merged[k] = v end
            return merged
        end
    end
    local copy = {}
    for k, v in pairs(DEFAULT_STYLE) do copy[k] = v end
    return copy
end

local function generate_title_card(text, output_path, background_path, style_name)
    local log = get_logger()
    local style = load_style(style_name)
    local dur = style.duration_sec
    local w, h = style.width, style.height

    local escaped = text:gsub("\\", "\\\\\\\\"):gsub(":", "\\\\:"):gsub("'", "\\\\'")

    local drawtext = string.format(
        "drawtext=text='%s':fontfile='':font='%s':fontsize=%d:fontcolor=%s"
        .. ":borderw=%d:bordercolor=%s:x=(w-text_w)/2:y=(h-text_h)/2",
        escaped, style.font, style.fontsize, style.fontcolor,
        style.borderw, style.bordercolor
    )

    local cmd
    if background_path and background_path ~= "" and file_exists(background_path) then
        cmd = string.format(
            'ffmpeg -y -i "%s" -t %d -vf "scale=%d:%d,%s" -c:v libx264 -preset fast -an "%s"',
            background_path, dur, w, h, drawtext, output_path)
    else
        cmd = string.format(
            'ffmpeg -y -f lavfi -i "color=c=%s:s=%dx%d:d=%d:r=25" -vf "%s" -c:v libx264 -preset fast -an "%s"',
            style.bg_color, w, h, dur, drawtext, output_path)
    end

    local result, code = shell_exec(cmd)
    if code ~= 0 then
        log:error("Ошибка ffmpeg: " .. (result:sub(1, 300) or ""))
        error("Не удалось сгенерировать титульную карточку")
    end
    log:info("Титульная карточка сгенерирована: " .. output_path)
    return output_path
end

local function detect_chapters_from_subtitles(srt_path, min_gap_ms)
    min_gap_ms = min_gap_ms or 5000
    local blocks = read_srt(srt_path)
    if #blocks == 0 then return {} end

    local chapters = {{title = "Introduction", start_ms = 0}}
    local num = 1
    for i = 2, #blocks do
        local gap = blocks[i].start_ms - blocks[i - 1].end_ms
        if gap >= min_gap_ms then
            num = num + 1
            local words = {}
            for w in blocks[i].text:gmatch("%S+") do
                words[#words + 1] = w
                if #words >= 5 then break end
            end
            local title = table.concat(words, " ")
            if #title > 40 then title = title:sub(1, 37) .. "..." end
            chapters[#chapters + 1] = {
                title = "Chapter " .. num .. ": " .. title,
                start_ms = blocks[i].start_ms,
            }
        end
    end
    return chapters
end

local function create_chapter_titles(chapters, working_dir, background_path, style_name, fps)
    local log = get_logger()
    local mp = get_media_pool()
    local timeline = get_current_timeline()
    if not timeline then error("Нет активного таймлайна для титульных карточек") end

    fps = fps or 25.0
    if not chapters or #chapters == 0 then
        log:info("Главы не определены — пропускаем титульные карточки")
        return 0
    end

    local titles_dir = join_path(working_dir, "generated_titles")
    mkdir_p(titles_dir)

    while timeline:GetTrackCount("video") < 4 do timeline:AddTrack("video") end

    local ae_bin = find_bin("AutoEditor")
    local t_bin = find_bin("Titles", ae_bin)
    mp:SetCurrentFolder(t_bin)

    log:info("Генерация " .. #chapters .. " титульных карточек глав...")

    local clip_infos = {}
    for i, chapter in ipairs(chapters) do
        local title = chapter.title or ("Chapter " .. i)
        local card_path = join_path(titles_dir, string.format("title_%03d.mp4", i))

        local ok, err = pcall(generate_title_card, title, card_path, background_path, style_name)
        if not ok then log:warning("Ошибка генерации титра " .. i .. ": " .. tostring(err)); goto continue end

        local clips = mp:ImportMedia({card_path})
        if not clips or #clips == 0 then log:warning("Не удалось импортировать: " .. card_path); goto continue end

        local style = load_style(style_name)
        clip_infos[#clip_infos + 1] = {
            mediaPoolItem = clips[1],
            startFrame = 0,
            endFrame = math.floor(style.duration_sec * fps),
            trackIndex = 4,
            recordFrame = ms_to_frames(chapter.start_ms or 0, fps),
            mediaType = 1,
        }
        ::continue::
    end

    if #clip_infos > 0 then
        local result = mp:AppendToTimeline(clip_infos)
        if result then log:info("Размещено " .. #clip_infos .. " титульных карточек на V4")
        else log:error("Не удалось разместить титульные карточки"); return 0 end
    end

    timeline:SetTrackEnable("audio", 4, false)
    log:info("Шаг 10 завершён: создано " .. #clip_infos .. " титульных карточек")
    return #clip_infos
end

--------------------------------------------------------------------------------
-- Определения шагов
--------------------------------------------------------------------------------
local STEPS = {
    {key = "1_import",      label = "1. Импорт медиа"},
    {key = "2_sync",        label = "2. Синхронизация аудио"},
    {key = "3_silence",     label = "3. Обнаружение тишины"},
    {key = "4_cut_silence", label = "4. Нарезка тишины"},
    {key = "5_subtitles",   label = "5. Субтитры"},
    {key = "6_ai_clean",    label = "6. Очистка ИИ"},
    {key = "7_ai_cut",      label = "7. Нарезка мусора"},
    {key = "8_multicam",    label = "8. Мультикамера"},
    {key = "9_zoom",        label = "9. Динамический зум"},
    {key = "10_transitions",label = "10. Переходы"},
    {key = "11_titles",     label = "11. Титульные карточки"},
}

local STATUS_COLORS = {
    pending = "#888888",
    running = "#FFB800",
    done    = "#00CC66",
    error   = "#FF4444",
}

--------------------------------------------------------------------------------
-- UI (Resolve UIManager)
--------------------------------------------------------------------------------
local function build_and_run_ui()
    local fusion = get_resolve():Fusion()
    local ui = fusion.UIManager
    local disp = bmd.UIDispatcher(ui)
    local config = Config.new()
    local running = false

    -- Настройка логгера
    setup_logger(config:get("working_dir", ""))

    -- ── Файлы ──
    local file_group = ui:VGroup({ID = "FileGroup"}, {
        ui:Label({Text = "AutoEditor — DaVinci Resolve", Weight = 0,
            Font = ui:Font({Family = "Arial", PixelSize = 18})}),
        ui:HGroup({
            ui:Label({Text = "Основное видео:", Weight = 0, MinimumSize = {140, 0}}),
            ui:LineEdit({ID = "MainVideoPath", PlaceholderText = "Путь к основному видео..."}),
            ui:Button({ID = "BrowseMainVideo", Text = "...", MaximumSize = {30, 24}}),
        }),
        ui:HGroup({
            ui:Label({Text = "Скринкаст:", Weight = 0, MinimumSize = {140, 0}}),
            ui:LineEdit({ID = "ScreencastPath", PlaceholderText = "Путь к скринкасту (необязательно)..."}),
            ui:Button({ID = "BrowseScreencast", Text = "...", MaximumSize = {30, 24}}),
        }),
        ui:HGroup({
            ui:Label({Text = "Рабочая папка:", Weight = 0, MinimumSize = {140, 0}}),
            ui:LineEdit({ID = "WorkingDir", PlaceholderText = "Директория для выходных файлов..."}),
            ui:Button({ID = "BrowseWorkingDir", Text = "...", MaximumSize = {30, 24}}),
        }),
    })

    -- ── Ресурсы ──
    local assets_group = ui:VGroup({ID = "AssetsGroup"}, {
        ui:Label({Text = "Ресурсы", Weight = 0, Font = ui:Font({Family = "Arial", PixelSize = 14})}),
        ui:HGroup({
            ui:Label({Text = "Переход:", Weight = 0, MinimumSize = {140, 0}}),
            ui:LineEdit({ID = "TransitionPath", PlaceholderText = "Видео перехода (.mov/.mp4)..."}),
            ui:Button({ID = "BrowseTransition", Text = "...", MaximumSize = {30, 24}}),
        }),
        ui:HGroup({
            ui:Label({Text = "Фон титров:", Weight = 0, MinimumSize = {140, 0}}),
            ui:LineEdit({ID = "TitleBgPath", PlaceholderText = "Фон для титров (необязательно)..."}),
            ui:Button({ID = "BrowseTitleBg", Text = "...", MaximumSize = {30, 24}}),
        }),
        ui:HGroup({
            ui:Label({Text = "Стиль титров:", Weight = 0, MinimumSize = {140, 0}}),
            ui:ComboBox({ID = "TitleStyle"}),
        }),
    })

    -- ── Настройки ──
    local settings_group = ui:VGroup({ID = "SettingsGroup"}, {
        ui:Label({Text = "Настройки", Weight = 0, Font = ui:Font({Family = "Arial", PixelSize = 14})}),
        ui:HGroup({
            ui:CheckBox({ID = "SilenceManual", Text = "Порог тишины вручную", Weight = 0}),
        }),
        ui:HGroup({ID = "SilenceRow"}, {
            ui:Label({Text = "Порог дБ:", Weight = 0, MinimumSize = {140, 0}}),
            ui:SpinBox({ID = "SilenceDb", Minimum = -80, Maximum = 0, Value = -40}),
            ui:Label({Text = "Мин. мс:", Weight = 0}),
            ui:SpinBox({ID = "SilenceMs", Minimum = 100, Maximum = 5000, Value = 500, SingleStep = 100}),
        }),
        ui:HGroup({
            ui:Label({Text = "Масштаб:", Weight = 0, MinimumSize = {140, 0}}),
            ui:DoubleSpinBox({ID = "ZoomMin", Minimum = 1.0, Maximum = 2.0, Value = 1.0, SingleStep = 0.05}),
            ui:Label({Text = "—", Weight = 0}),
            ui:DoubleSpinBox({ID = "ZoomMax", Minimum = 1.0, Maximum = 2.0, Value = 1.3, SingleStep = 0.05}),
        }),
        ui:HGroup({
            ui:CheckBox({ID = "SwitchManual", Text = "Переключение вручную", Weight = 0}),
        }),
        ui:HGroup({ID = "SwitchRow"}, {
            ui:Label({Text = "Переключ. сек:", Weight = 0, MinimumSize = {140, 0}}),
            ui:SpinBox({ID = "SwitchMin", Minimum = 1, Maximum = 60, Value = 5}),
            ui:Label({Text = "—", Weight = 0}),
            ui:SpinBox({ID = "SwitchMax", Minimum = 1, Maximum = 120, Value = 15}),
        }),
    })

    -- ── Шаги ──
    local step_rows = {}
    for _, st in ipairs(STEPS) do
        step_rows[#step_rows + 1] = ui:HGroup({
            ui:Label({ID = "Status_" .. st.key, Text = "\xe2\x97\x8f", Weight = 0,
                MinimumSize = {20, 0},
                StyleSheet = "color: " .. STATUS_COLORS.pending .. "; font-size: 16px;"}),
            ui:Button({ID = "Btn_" .. st.key, Text = st.label, MinimumSize = {200, 28}}),
        })
    end

    step_rows[#step_rows + 1] = ui:HGroup({
        ui:Button({ID = "RunAll", Text = "Запустить все", MinimumSize = {200, 32},
            StyleSheet = "background-color: #2d5aa0; color: white;"}),
        ui:Button({ID = "ResetSteps", Text = "Сброс", MaximumSize = {80, 32}}),
    })

    local steps_group = ui:VGroup({ID = "StepsGroup"},
        {ui:Label({Text = "Шаги", Weight = 0,
            Font = ui:Font({Family = "Arial", PixelSize = 14})}),
         table.unpack(step_rows)})

    -- ── Лог ──
    local log_group = ui:VGroup({ID = "LogGroup"}, {
        ui:Label({Text = "Журнал", Weight = 0, Font = ui:Font({Family = "Arial", PixelSize = 14})}),
        ui:TextEdit({ID = "LogArea", ReadOnly = true,
            Font = ui:Font({Family = "Courier", PixelSize = 11}),
            MinimumSize = {0, 200}}),
        ui:Button({ID = "ClearLog", Text = "Очистить", MaximumSize = {100, 24}}),
    })

    -- ── Главное окно ──
    local win = disp:AddWindow(
        {ID = "AutoEditorWin", WindowTitle = "AutoEditor", Geometry = {200, 100, 700, 900}},
        ui:VGroup({file_group, assets_group, settings_group, ui:HGroup({steps_group, log_group})})
    )

    local items = win:GetItems()

    -- Заполнить стили титров
    items.TitleStyle:AddItem("default")
    local styles_content = read_file(STYLES_FILE)
    if styles_content then
        local ok, styles_data = pcall(json.decode, styles_content)
        if ok and styles_data then
            for name in pairs(styles_data) do
                if name ~= "default" then items.TitleStyle:AddItem(name) end
            end
        end
    end

    -- ── Загрузка конфига в UI ──
    local function load_config_to_ui()
        items.MainVideoPath.Text = config:get("main_video_path", "")
        items.ScreencastPath.Text = config:get("screencast_path", "")
        items.WorkingDir.Text = config:get("working_dir", "")
        items.TransitionPath.Text = config:get("transition_video_path", "")
        items.TitleBgPath.Text = config:get("title_background_path", "")
        items.SilenceManual.Checked = config:get("silence_manual", false)
        items.SilenceDb.Value = config:get("silence_threshold_db", -40)
        items.SilenceMs.Value = config:get("silence_min_duration_ms", 500)
        items.SilenceRow.Hidden = not config:get("silence_manual", false)
        items.ZoomMin.Value = config:get("zoom_min", 1.0)
        items.ZoomMax.Value = config:get("zoom_max", 1.3)
        items.SwitchManual.Checked = config:get("multicam_manual", false)
        items.SwitchMin.Value = config:get("multicam_min_interval", 5)
        items.SwitchMax.Value = config:get("multicam_max_interval", 15)
        items.SwitchRow.Hidden = not config:get("multicam_manual", false)

        for _, st in ipairs(STEPS) do
            local status = config:get_step_status(st.key)
            local color = STATUS_COLORS[status] or STATUS_COLORS.pending
            items["Status_" .. st.key].StyleSheet = "color: " .. color .. "; font-size: 16px;"
        end
    end

    local function save_config_from_ui()
        config:set("main_video_path", items.MainVideoPath.Text)
        config:set("screencast_path", items.ScreencastPath.Text)
        config:set("working_dir", items.WorkingDir.Text)
        config:set("transition_video_path", items.TransitionPath.Text)
        config:set("title_background_path", items.TitleBgPath.Text)
        config:set("silence_manual", items.SilenceManual.Checked)
        config:set("silence_threshold_db", items.SilenceDb.Value)
        config:set("silence_min_duration_ms", items.SilenceMs.Value)
        config:set("zoom_min", items.ZoomMin.Value)
        config:set("zoom_max", items.ZoomMax.Value)
        config:set("multicam_manual", items.SwitchManual.Checked)
        config:set("multicam_min_interval", items.SwitchMin.Value)
        config:set("multicam_max_interval", items.SwitchMax.Value)
        config:save()
    end

    local function log_to_ui(msg)
        if items.LogArea then items.LogArea:Append(msg .. "\n") end
    end
    set_ui_callback(log_to_ui)

    local function update_status(step_key, status)
        local color = STATUS_COLORS[status] or STATUS_COLORS.pending
        items["Status_" .. step_key].StyleSheet = "color: " .. color .. "; font-size: 16px;"
    end

    -- ── Обработчики шагов ──
    local step_runners = {}

    step_runners["1_import"] = function()
        import_media(config:get("main_video_path"), config:get("screencast_path"))
    end

    step_runners["2_sync"] = function()
        auto_sync_audio(find_tagged_clips(), config)
    end

    step_runners["3_silence"] = function()
        local video_path = config:get("main_video_path")
        local threshold
        if config:get("silence_manual", false) then
            threshold = config:get("silence_threshold_db", -40)
        else
            threshold = auto_detect_threshold(video_path)
        end
        detect_silence(video_path, threshold,
            config:get("silence_min_duration_ms", 500),
            config:get("working_dir"))
    end

    step_runners["4_cut_silence"] = function()
        local clips = find_tagged_clips()
        local main_clip = clips.main
        if not main_clip then error("Основной клип не найден в медиапуле") end
        local total_ms = get_clip_duration_ms(main_clip)
        local fps = get_fps()
        local keep = compute_silence_keep_segments(config:get("working_dir"), total_ms, fps)
        rebuild_timeline(main_clip, keep, "AutoEditor_Clean", fps,
            clips.screencast, config:get("audio_offset_ms", 0))
    end

    step_runners["5_subtitles"] = function()
        generate_subtitles(config:get("subtitle_language", "Russian"))
        export_subtitles(config:get("working_dir"), "original.srt")
    end

    step_runners["6_ai_clean"] = function()
        run_ai_cleanup(
            config:working_path("original.srt"),
            config:working_path("cleaned.srt"),
            config:get("openrouter_api_key"),
            config:get("openrouter_model"),
            config:get("ai_chunk_size", 50))
    end

    step_runners["7_ai_cut"] = function()
        local clips = find_tagged_clips()
        local main_clip = clips.main
        if not main_clip then error("Основной клип не найден в медиапуле") end
        local total_ms = get_clip_duration_ms(main_clip)
        local fps = get_fps()
        local keep = compute_ai_keep_segments(config:get("working_dir"), total_ms, fps)
        rebuild_timeline(main_clip, keep,
            config:get("timeline_name", "AutoEditor_Final"), fps,
            clips.screencast, config:get("audio_offset_ms", 0))
    end

    step_runners["8_multicam"] = function()
        local clips = find_tagged_clips()
        if not clips.screencast then
            get_logger():info("Скринкаст отсутствует — пропускаем мультикамеру"); return
        end
        local keep = load_keep_segments(config:get("working_dir"))
        local min_iv, max_iv
        if config:get("multicam_manual", false) then
            min_iv = config:get("multicam_min_interval", 5)
            max_iv = config:get("multicam_max_interval", 15)
        else
            min_iv, max_iv = auto_switch_intervals(keep)
        end
        distribute_multicam(clips.screencast, keep,
            min_iv, max_iv, get_fps(),
            config:get("audio_offset_ms", 0))
    end

    step_runners["9_zoom"] = function()
        apply_dynamic_zoom(config:get("zoom_min", 1.0), config:get("zoom_max", 1.3))
    end

    step_runners["10_transitions"] = function()
        local tr_path = config:get("transition_video_path")
        if not tr_path or tr_path == "" then
            get_logger():info("Видео перехода не указано — пропускаем"); return
        end
        local tr_clip = import_transition_video(tr_path)
        apply_transitions(tr_clip, get_fps())
    end

    step_runners["11_titles"] = function()
        local wd = config:get("working_dir")
        local cleaned = config:working_path("cleaned.srt")
        local original = config:working_path("original.srt")
        local srt = file_exists(cleaned) and cleaned or original
        local chapters = {}
        if file_exists(srt) then chapters = detect_chapters_from_subtitles(srt) end
        create_chapter_titles(chapters, wd,
            config:get("title_background_path", ""),
            config:get("title_style", "default"), get_fps())
    end

    -- ── Запуск шага ──
    local function run_step(step_key)
        running = true
        config:set_step_status(step_key, "running")
        update_status(step_key, "running")

        local log = get_logger()
        local label = step_key
        for _, st in ipairs(STEPS) do
            if st.key == step_key then label = st.label; break end
        end
        log:info("=== Запуск: " .. label .. " ===")

        local runner = step_runners[step_key]
        if not runner then
            config:set_step_status(step_key, "error")
            update_status(step_key, "error")
            log:error("Нет обработчика для шага: " .. step_key)
            running = false
            return
        end

        local ok, err = pcall(runner)
        if ok then
            config:set_step_status(step_key, "done")
            update_status(step_key, "done")
            log:info("=== Завершён: " .. label .. " ===")
        else
            config:set_step_status(step_key, "error")
            update_status(step_key, "error")
            log:error("=== Ошибка: " .. label .. " — " .. tostring(err) .. " ===")
        end
        running = false
    end

    -- ── Подключение событий ──
    function win.On.AutoEditorWin.Close(ev)
        save_config_from_ui()
        disp:ExitLoop()
    end

    function win.On.ClearLog.Clicked(ev)
        items.LogArea:Clear()
    end

    function win.On.ResetSteps.Clicked(ev)
        config:reset_steps()
        for _, st in ipairs(STEPS) do update_status(st.key, "pending") end
        log_to_ui("[" .. os.date("%H:%M:%S") .. "] INFO    Все шаги сброшены в состояние ожидания.")
    end

    local function browse(field_id, folder)
        local path
        if folder then path = fusion:RequestDir()
        else path = fusion:RequestFile() end
        if path then items[field_id].Text = tostring(path) end
    end

    function win.On.SilenceManual.Clicked(ev)
        items.SilenceRow.Hidden = not items.SilenceManual.Checked
    end
    function win.On.SwitchManual.Clicked(ev)
        items.SwitchRow.Hidden = not items.SwitchManual.Checked
    end

    function win.On.BrowseMainVideo.Clicked(ev) browse("MainVideoPath") end
    function win.On.BrowseScreencast.Clicked(ev) browse("ScreencastPath") end
    function win.On.BrowseWorkingDir.Clicked(ev) browse("WorkingDir", true) end
    function win.On.BrowseTransition.Clicked(ev) browse("TransitionPath") end
    function win.On.BrowseTitleBg.Clicked(ev) browse("TitleBgPath") end

    -- Кнопки шагов
    for _, st in ipairs(STEPS) do
        win.On["Btn_" .. st.key] = {
            Clicked = function(ev)
                if running then log_to_ui("Другой шаг уже выполняется."); return end
                save_config_from_ui()
                run_step(st.key)
            end
        }
    end

    function win.On.RunAll.Clicked(ev)
        if running then log_to_ui("Шаги уже выполняются."); return end
        save_config_from_ui()
        running = true
        for _, st in ipairs(STEPS) do
            if not running then break end
            local status = config:get_step_status(st.key)
            if status == "done" then
                log_to_ui("[" .. os.date("%H:%M:%S") .. "] INFO    Пропуск: " .. st.label .. " (уже выполнен)")
            else
                run_step(st.key)
                if config:get_step_status(st.key) == "error" then
                    log_to_ui("[" .. os.date("%H:%M:%S") .. "] INFO    Остановка: ошибка в " .. st.label)
                    break
                end
            end
        end
        running = false
    end

    load_config_to_ui()
    win:Show()
    disp:RunLoop()
    win:Hide()
end

--------------------------------------------------------------------------------
-- Точка входа
--------------------------------------------------------------------------------
build_and_run_ui()

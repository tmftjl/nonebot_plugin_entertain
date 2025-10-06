import fetch from 'node-fetch'
import path from 'path' // 仅用于部分框架的兼容，如果不需要可移除

// 存储用户搜索结果
const UserMusicResults = {};

export class MusicShare extends plugin {
   constructor() {
      super({
         name: '综合点歌',
         dsc: '点歌',
         event: 'message',
         priority: -10000,
         rule: [
            {
               // 使用优化后的正则表达式，能清晰地分离平台和关键词
               reg: '^#?点歌(?:(qq|酷狗|网易|wyy|kugou|netease))?\\s*(.*)$',
               fnc: 'searchMusic'
            },
            {
               reg: '^#?听([0-9]+)$',
               fnc: 'playMusic'
            }
         ]
      })
   }

   async searchMusic(e) {
    const regex = /^#?点歌(?:(qq|酷狗|网易|wyy|kugou|netease))?\s*(.*)$/;
    const match = regex.exec(e.msg);

    const platformInput = match[1] || '';
    let keyword = match[2]?.trim();

      if (!keyword) {
         await e.reply('请输入要搜索的歌曲名，例如：#点歌 晴天');
         return
      }

      const urlList = {
         qq: 'http://datukuai.top:1450/djs/API/QQ_Music/api.php?msg=paramsSearch&limit=30',
         kugou: 'http://mobilecdn.kugou.com/api/v3/search/song?format=json&keyword=paramsSearch&page=1&pagesize=10&showtype=1',
         wangyiyun: 'http://datukuai.top:3000/search?keywords=paramsSearch'
      }

    let apiName = '';
    
    // 根据捕获到的平台关键词，确定apiName
    if (['qq'].includes(platformInput.toLowerCase())) {
        apiName = 'qq';
    } else if (['酷狗', 'kugou'].includes(platformInput.toLowerCase())) {
        apiName = 'kugou';
    } else if (['网易', 'wyy', 'netease'].includes(platformInput.toLowerCase())) {
        apiName = 'wangyiyun';
    } else {
        // 如果没有指定平台，或平台无效，则使用默认平台（例如网易云）
        apiName = 'wangyiyun';
    }

      try {
         let encodedKeyword = encodeURI(keyword)
         let url = urlList[apiName].replace("paramsSearch", encodedKeyword)
         let response = await fetch(url)
         const { data, result } = await response.json()

         let songs = []
         if (apiName === 'kugou') {
            songs = data.info
         } else if (apiName === 'qq') {
            songs = data
         } else { // wangyiyun
            songs = result.songs
         }
      
      if (!songs || songs.length === 0) {
        const platformNameForReply = apiName === 'qq' ? 'QQ音乐' : apiName === 'kugou' ? '酷狗音乐' : '网易云音乐';
        await e.reply(`在【${platformNameForReply}】中没有找到与“${keyword}”相关的歌曲。`);
        return;
      }

         UserMusicResults[e.user_id] = { type: apiName, songs: songs }

      const songListText = songs.map((song, index) => {
        let name = apiName === 'kugou' ? song.songname : apiName === 'qq' ? song.song : song.name
        let artist = apiName === 'kugou' ? song.singername : apiName === 'qq' ? song.singers : (song.artists && song.artists[0] ? song.artists[0].name : '未知艺人')
        return `${index + 1}. ${name} - ${artist}`
      }).slice(0, 20).join('\n');

      const platformName = apiName === 'qq' ? 'QQ音乐' : apiName === 'kugou' ? '酷狗音乐' : '网易云音乐';
      const replyText = `为你从【${platformName}】找到以下歌曲：\n--------------------\n${songListText}\n--------------------\n请发送“#听序号”来播放，如：#听1`;
         await e.reply(replyText);

      } catch (err) {
         console.log(err)
         await e.reply('搜索歌曲时发生错误，请稍后再试。');
      }
   }

   async playMusic(e) {
      if (!UserMusicResults[e.user_id]) {
         await e.reply('您的点歌记录已过期，请先搜索歌曲。\n例如：#点歌 晴天');
         return
      }

      let index = parseInt(e.msg.replace(/^#?听/, "")) - 1
      let { type, songs } = UserMusicResults[e.user_id]

      if (index < 0 || index >= songs.length) {
         await e.reply('无效的歌曲序号，请检查后重试。');
         return
      }

      let song = songs[index]
    let songName = type === 'kugou' ? song.songname : type === 'qq' ? song.song : song.name
    let artist = type === 'kugou' ? song.singername : type === 'qq' ? song.singers : (song.artists && song.artists[0] ? song.artists[0].name : '未知艺人')

      await e.reply(`正在获取：${songName} - ${artist}\n请稍候...`);

      try {
         if (type === 'wangyiyun') {
        // 网易云音乐Cookie已内置
            const wyck = '0050705497FF5123F4341A4B3A03817F1AA12AED60AEDC0D0877CE692D0CF08D06E45D2864FF1F61279CA7FA'+
            '1337EF37F500DBB94BD186EF01E1D2F3153276C3CD2BBD407D6B929F55FAE52761DC6C669BDD15B8D1671B13B5536BD3D10E63'+
            'B8910CF7C86FFD1EF0715F6E1A16398CDECE1A40DA4F0042A5D9378FA0FD102E3F5CF5C33CB779A37B0789421AB2C5C22D6763'+
            '4D2D105B4A2FDB02F62E88F9652EF8600640394A5116594682B1B4E9A52061B81AF945ED21F8EE99B53767039E0669BB61E620'+
            '3BDD1A3A6CE95B11DA6F2E1A8ECD59AFA8184BB6D3BB3CE807589265023165250D59FBA2F5D756F4DC65DF60A9DBFBEE64135E'+
            'D944F478FE9F45D9FACF4DB1A6744F8AEDA04730BC8AFE5A7D82CE20E77C75660208EA1774A92541542924221622AAB0F7C081'+
            '56D1039CFC19A229D5C99CA59E463760CFDC951606853DC16BE0A50C70E5745881B1E439F609';

            let ids = String(song.id)
            let url = 'http://music.163.com/song/media/outer/url?id=' + ids
            let options = {
               method: 'POST',
               headers: {
                  'Content-Type': 'application/x-www-form-urlencoded',
                  'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 12; MI Build/SKQ1.211230.001)',
                  'Cookie': 'versioncode=8008070; os=android; channel=xiaomi; appver=8.8.70; MUSIC_U=' + wyck
               },
               body: `ids=${JSON.stringify([ids])}&level=standard&encodeType=mp3`
            }
            let response = await fetch('https://music.163.com/api/song/enhance/player/url/v1', options)
            let res = await response.json()
            if (res.code == 200 && res.data[0]?.url) {
               url = res.data[0].url
            } else {
          await e.reply(`网易云获取链接失败，可能Cookie已失效。代码: ${res.code}`);
          return;
        }

            await this.sendAudioAndCard(e, 'netease', { ...song, url, ids });

         } else if (type === 'qq') {
            let url = `http://datukuai.top:1450/djs/API/QQ_Music/api.php?msg=${encodeURI(song.song)}&n=1&q=7`
            let response = await fetch(url)
            let data = await response.json()
            await this.sendAudioAndCard(e, 'qq', { ...song, url: data.data.music });

         } else if (type === 'kugou') {
            let url = `https://wenxin110.top/api/kugou_music?msg=${encodeURI(song.songname)}&n=1`
            let response = await fetch(url)
            let result = await response.text()
            result = result.replace(/±/g, "").replace(/\\/g, "").replace(/img=/g, "").replace(/播放地址：/g, "")
            let data = result.split('n')
            await this.sendAudioAndCard(e, 'kugou', { ...song, url: data[3], pic: data[0], name: data[1], artist: data[2] });
         }

      } catch (err) {
         console.log(err)
         await e.reply('播放歌曲时发生未知错误，请稍后再试。');
      }
   }

  // 辅助函数，用于发送语音和卡片，避免代码重复
  async sendAudioAndCard(e, source, songData) {
    // 1. 发送语音
    try {
      let msg = await segment.record(songData.url);
      await e.reply(msg);
    } catch (err) {
      await e.reply('播放失败：歌曲文件过大或链接失效，无法发送语音。');
      return; // 语音发送失败，后续卡片也可能没有意义，可以选择返回
    }

    // 2. 准备分享卡片的数据
    let shareData = {};
    if (source === 'netease') {
      shareData = {
        source, name: songData.name, artist: songData.artists[0].name,
        pic: songData.al?.picUrl ?? songData.artists?.[0]?.img1v1Url, link: 'https://music.163.com/#/song?id=' + songData.ids, url: songData.url
      }
    } else if (source === 'qq') {
      shareData = {
        source, name: songData.song, artist: songData.singers,
        pic: songData.picture, link: "https://y.qq.com/n/ryqq/songDetail/" + songData.mid, url: songData.url
      }
    } else if (source === 'kugou') {
      shareData = {
        source, name: songData.name, artist: songData.artist,
        pic: songData.pic, link: "http://www.kugou.com/song", url: songData.url
      }
    }
    
    // 3. 发送分享卡片
    await this.sendMusicShare(e, shareData);
  }

   async sendMusicShare(e, data) {
      if (!e.bot.sendOidb) return false

      let appid, appname, appsign, style = 4
      switch (data.source) {
         case 'netease': appid = 100495085; appname = "com.netease.cloudmusic"; appsign = "da6b069da1e2982db3e386233f68d76d"; break;
         case 'kugou': appid = 205141; appname = "com.kugou.android"; appsign = "fe4a24d80fcf253a00676a808f62c2c6"; break;
         default: appid = 100497308; appname = "com.tencent.qqmusic"; appsign = "cbd27cd7c861227d013a25b2d10f0799"; break;
      }

      let body = {
         1: appid, 2: 1, 3: style,
         5: { 1: 1, 2: "0.0.0", 3: appname, 4: appsign },
         10: e.isGroup ? 1 : 0,
         11: e.isGroup ? e.group_id : e.user_id,
         12: {
            10: data.name, 11: data.artist, 12: '[分享]' + data.name + '-' + data.artist,
            13: data.link, 14: data.pic, 16: data.url
         }
      }
    
    // 假设您的框架核心变量是 core
      let payload = await e.bot.sendOidb("OidbSvc.0xb77_9", core.pb.encode(body))
      let result = core.pb.decode(payload)

      if (result[3] != 0) {
         await e.reply(`歌曲分享卡片发送失败，错误码：${result[3]}`);
      }
   }
}
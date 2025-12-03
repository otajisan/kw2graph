'use client';

import React, {useState, useCallback, useTransition, useEffect, useRef} from 'react';
import axios, {AxiosError} from 'axios';

// Material UI のコンポーネントをインポート
import {
    Box,
    Button,
    Container,
    TextField,
    Typography,
    Paper,
    CircularProgress,
    Stack,
    List,
    ListItem,
    Chip,
    Alert,
    Divider,
    Grid
} from '@mui/material';

// APIのベースURL。FastAPIが動いているURLを指定
const API_BASE_URL = 'http://localhost:8000';

// --- 型定義 ---
// (中略 - 変更なし)
interface Candidate {
    videoId: string;
    snippet: { title: string; };
}

interface CandidateResponse {
    seed_keyword: string;
    candidates: Candidate[];
}

interface AnalyzeKeywordsOutputItem {
    keyword: string;
    score: number;
    // ★ 修正: 新しい属性を追加
    iab_categories: string[];
    entity_type: 'Proper' | 'General';
}

interface AnalyzeKeywordsOutput {
    seed_keyword: string;
    results: AnalyzeKeywordsOutputItem[];
}

interface CreateGraphOutput {
    result: boolean;
}

interface CreateGraphInput {
    seed_keyword: string;
    children: {
        keyword: string;
        score: number;
        // ★ 修正: 登録時にiab_categoriesとentity_typeを渡すよう拡張
        iab_categories: string[];
        entity_type: 'Proper' | 'General';
    }[];
}

interface GraphNode {
    id: string;
    label: string;
    group: string;
    entity_type: string;
    iab_categories: string[];
}

interface GraphEdge {
    id: string;
    from_node: string;
    to_node: string;
    score: number;
}

interface ShowGraphOutput {
    nodes: GraphNode[];
    edges: GraphEdge[];
}

// --- 型定義 終わり ---


// --- メインコンポーネント ---

export default function Home() {
    const [keyword, setKeyword] = useState<string>('');
    // 💡 maxDepth State を追加 (デフォルト値 2 に対応)
    const [maxDepth, setMaxDepth] = useState<number>(2);
    const [minScore, setMinScore] = useState<number>(0.5);
    const [entityTypeFilter, setEntityTypeFilter] = useState<'all' | 'Proper' | 'General'>('all');
    const [iabCategoryFilter, setIabCategoryFilter] = useState<string>(''); // 選択されたIABカテゴリ

    const [candidateData, setCandidateData] = useState<CandidateResponse | null>(null);
    const [analyzeData, setAnalyzeData] = useState<AnalyzeKeywordsOutput | null>(null);
    const [graphData, setGraphData] = useState<ShowGraphOutput | null>(null);

    const [error, setError] = useState<string | null>(null);

    const [isPending, startTransition] = useTransition();
    const [isAnalyzePending, startAnalyzeTransition] = useTransition();
    const [isCreatePending, startCreateTransition] = useTransition();
    const [isGraphPending, startGraphTransition] = useTransition();

    const [createStatus, setCreateStatus] = useState<'idle' | 'success' | 'failure'>('idle');


    // --- API関数群 ---
    // (handleAxiosError は省略 - 変更なし)
    const handleAxiosError = (err: unknown, apiName: string) => {
        if (axios.isAxiosError(err)) {
            const axiosError = err as AxiosError;
            const status = axiosError.response?.status;
            const data = axiosError.response?.data;
            const message = `HTTPエラー (${status}): ${data ? JSON.stringify(data) : axiosError.message}`;
            setError(`${apiName} APIリクエスト失敗: ${message}`);
        } else {
            setError(`予期せぬエラー: ${err instanceof Error ? err.message : '不明なエラー'}`);
        }
        console.error(`Axios Error (${apiName}):`, err);
    };

    // fetchCandidate (省略 - 変更なし)
    const fetchCandidate = useCallback(async (kw: string) => {
        setError(null);
        setCandidateData(null);
        setAnalyzeData(null);
        setGraphData(null);
        setCreateStatus('idle');

        const payload = {index: 'videos', field: 'snippet.title', keyword: kw};

        try {
            const response = await axios.post<CandidateResponse>(
                `${API_BASE_URL}/candidate`, payload,
                {headers: {'Content-Type': 'application/json'}}
            );
            setCandidateData(response.data);
        } catch (err) {
            handleAxiosError(err, 'Candidate');
        }
    }, []);

    // fetchAnalyze (省略 - 変更なし)
    const fetchAnalyze = useCallback(async (seedKeyword: string, titles: string[]) => {
        setAnalyzeData(null);
        setGraphData(null);
        setCreateStatus('idle');
        setError(null);

        const payload = {seed_keyword: seedKeyword, children: titles};

        try {
            const response = await axios.post<AnalyzeKeywordsOutput>(
                `${API_BASE_URL}/analyze`, payload,
                {
                    headers: {'Content-Type': 'application/json'},
                    timeout: 120000
                }
            );
            setAnalyzeData(response.data);
        } catch (err) {
            handleAxiosError(err, 'Analyze');
        }
    }, []);

    // fetchCreateGraph (省略 - 変更なし)
// fetchCreateGraph の修正
    const fetchCreateGraph = useCallback(async (data: AnalyzeKeywordsOutput) => {
        setCreateStatus('idle');
        setError(null);

        // ★ 修正: children に iab_categories と entity_type を含める
        const payload: CreateGraphInput = {
            seed_keyword: data.seed_keyword,
            children: data.results.map(item => ({
                keyword: item.keyword,
                score: item.score,
                iab_categories: item.iab_categories, // 新しい属性
                entity_type: item.entity_type,       // 新しい属性
            })),
        };

        try {
            // ... (後続の axios.post は省略 - 変更なし)
            const response = await axios.post<CreateGraphOutput>(
                `${API_BASE_URL}/create`, payload,
                {headers: {'Content-Type': 'application/json'}}
            );

            if (response.data.result === true) {
                setCreateStatus('success');
            } else {
                setCreateStatus('failure');
                setError('グラフ作成APIが失敗を返しました。');
            }

        } catch (err) {
            setCreateStatus('failure');
            handleAxiosError(err, 'Create Graph');
        }
    }, []);

    // 💡 Show Graph API のロジックを修正
    const fetchShowGraph = useCallback(async (seedKeyword: string, depth: number, score: number, entity: string, iab: string) => {
        setGraphData(null);
        setError(null);
        setCreateStatus('idle');

        // 💡 クエリパラメータに新しいフィルタを追加
        const params = new URLSearchParams({
            seed_keyword: seedKeyword,
            max_depth: depth.toString(),
            min_score: score.toString(), // 最小スコアを追加

        });

        if (entity !== 'all') {
            params.set('entity_type', entity); // entity_type フィルタを追加
        }
        if (iab.trim()) {
            params.set('iab_category', iab.trim()); // iab_category フィルタを追加
        }

        try {
            const response = await axios.get<ShowGraphOutput>(
                `${API_BASE_URL}/show_graph?${params.toString()}`,
                {headers: {'Content-Type': 'application/json'}}
            );

            setGraphData(response.data);

        } catch (err) {
            handleAxiosError(err, 'Show Graph');
        }
    }, []);


    // --- イベントハンドラ ---
    // (handleGetCandidate, handleAnalyze, handleCreateGraph は省略 - 変更なし)
    const handleGetCandidate = () => {
        if (!keyword.trim()) {
            setError('キーワードを入力してください。');
            return;
        }
        startTransition(() => {
            fetchCandidate(keyword);
        });
    };

    const handleAnalyze = () => {
        if (!candidateData || candidateData.candidates.length === 0) {
            setError('Analyzeを実行するには、先にCandidate検索を実行し、結果を取得してください。');
            return;
        }
        const titles = candidateData.candidates.map(c => c.snippet.title);

        startAnalyzeTransition(() => {
            fetchAnalyze(candidateData.seed_keyword, titles);
        });
    };

    const handleCreateGraph = () => {
        if (!analyzeData || analyzeData.results.length === 0) {
            setError('Create Graphを実行するには、Analyze検索を実行し、結果を取得してください。');
            return;
        }
        startCreateTransition(() => {
            fetchCreateGraph(analyzeData);
        });
    };

    // 💡 Show Graph ボタンクリック時の処理を修正
    const handleShowGraph = () => {
        if (!keyword.trim()) {
            setError('グラフ表示を実行するには、検索キーワードを入力してください。');
            return;
        }

        startGraphTransition(() => {
            fetchShowGraph(
                keyword,
                maxDepth,
                minScore,
                entityTypeFilter,
                iabCategoryFilter
            );
        });
    };

    // 💡 maxDepth の入力変更ハンドラ
    const handleMaxDepthChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const value = parseInt(e.target.value, 10);
        // 0以上の整数に限定
        if (!isNaN(value) && value >= 0) {
            setMaxDepth(value);
        } else if (e.target.value === '') {
            // 入力が空の場合は0として扱う（またはFastAPIのデフォルト値に依存）
            setMaxDepth(0);
        }
    };

    // 💡 最小スコアの入力変更ハンドラ
    const handleMinScoreChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const value = parseFloat(e.target.value);
        if (!isNaN(value) && value >= 0 && value <= 1.0) {
            setMinScore(value);
        }
    };


    return (
        <Container maxWidth="md" sx={{py: 4, minHeight: '100vh', bgcolor: '#f5f5f5'}}>
            <Paper elevation={3} sx={{p: {xs: 2, md: 4}, borderRadius: 2}}>

                {/* タイトル */}
                <Typography variant="h3" component="h1" gutterBottom sx={{fontWeight: 'bold', color: '#0070f3'}}>
                    kw2graph
                </Typography>
                <Typography variant="subtitle1" color="text.secondary" sx={{mb: 3}}>
                    Next.js (MUI) と FastAPI (Python) 連携プロトタイプ
                </Typography>

                <Divider sx={{mb: 4}}/>

                {/* 💡 キーワード入力と深さの入力フィールドを並べる */}
                <Grid container spacing={2} sx={{mb: 3}}>
                    <Grid item xs={12} sm={9}>
                        <TextField
                            fullWidth
                            label="検索キーワード (グラフの起点)"
                            variant="outlined"
                            value={keyword}
                            onChange={(e) => setKeyword(e.target.value)}
                            placeholder="例: 料理"
                            disabled={isPending || isAnalyzePending || isCreatePending || isGraphPending}
                            InputProps={{
                                startAdornment: <Box sx={{mr: 1, color: 'action.active'}}>🔍</Box>,
                            }}
                        />
                    </Grid>
                    <Grid item xs={12} sm={3}>
                        <TextField
                            fullWidth
                            label="最大深さ (max_depth)"
                            variant="outlined"
                            type="number"
                            value={maxDepth}
                            onChange={handleMaxDepthChange}
                            inputProps={{min: 0}}
                            disabled={isPending || isAnalyzePending || isCreatePending || isGraphPending}
                            helperText="デフォルト: 2"
                        />
                    </Grid>
                </Grid>

                {/* ボタン群 */}
                <Stack direction={{xs: 'column', sm: 'row'}} spacing={2} sx={{mb: 4}} useFlexGap>
                    {/* Candidate ボタン */}
                    <Button
                        variant="contained"
                        color="primary"
                        onClick={handleGetCandidate}
                        disabled={isPending || !keyword.trim()}
                        startIcon={isPending ? <CircularProgress size={20} color="inherit"/> : null}
                    >
                        {isPending ? '検索中...' : 'Get Candidate'}
                    </Button>

                    {/* Analyze ボタン */}
                    <Button
                        variant="contained"
                        sx={{bgcolor: '#ff9800', '&:hover': {bgcolor: '#e68a00'}}}
                        onClick={handleAnalyze}
                        disabled={!candidateData || isAnalyzePending || isPending || isCreatePending || isGraphPending}
                        startIcon={isAnalyzePending ? <CircularProgress size={20} color="inherit"/> : null}
                    >
                        {isAnalyzePending ? 'Analyze中...' : 'Analyze Titles'}
                    </Button>

                    {/* Create Graph ボタン */}
                    <Button
                        variant="contained"
                        color="success"
                        onClick={handleCreateGraph}
                        disabled={!analyzeData || isCreatePending || isPending || isAnalyzePending || isGraphPending}
                        startIcon={isCreatePending ? <CircularProgress size={20} color="inherit"/> : null}
                    >
                        {isCreatePending ? '登録中...' : 'Create Graph'}
                    </Button>

                    {/* Show Graph ボタン */}
                    <Button
                        variant="contained"
                        sx={{bgcolor: '#0097a7', '&:hover': {bgcolor: '#007983'}}}
                        onClick={handleShowGraph}
                        disabled={!keyword.trim() || isGraphPending || isPending || isAnalyzePending || isCreatePending}
                        startIcon={isGraphPending ? <CircularProgress size={20} color="inherit"/> : null}
                    >
                        {isGraphPending ? '描画中...' : 'Show Graph'}
                    </Button>
                </Stack>

                <Divider sx={{mb: 4}}/>

                {/* 💡 フィルタリング設定エリア */}
                <Typography variant="h6" component="h2"
                            sx={{mt: 4, mb: 2, color: 'text.secondary', fontWeight: 'bold'}}>
                    グラフフィルタ設定
                </Typography>
                <Grid container spacing={2} sx={{mb: 3}}>
                    {/* 最小スコアフィルタ */}
                    <Grid item xs={12} sm={4}>
                        <TextField
                            fullWidth
                            label="最小関連度スコア"
                            variant="outlined"
                            type="number"
                            value={minScore}
                            onChange={handleMinScoreChange}
                            inputProps={{min: 0.0, max: 1.0, step: 0.01}}
                            helperText="例: 0.5 (エッジのフィルタ)"
                        />
                    </Grid>
                    {/* エンティティ種別フィルタ */}
                    <Grid item xs={12} sm={4}>
                        <TextField
                            select
                            fullWidth
                            label="エンティティ種別"
                            variant="outlined"
                            value={entityTypeFilter}
                            onChange={(e) => setEntityTypeFilter(e.target.value as 'all' | 'Proper' | 'General')}
                            helperText="ノードのフィルタ (Proper/General)"
                            SelectProps={{native: true}}
                        >
                            <option value="all">すべて</option>
                            <option value="Proper">固有名詞 (Proper)</option>
                            <option value="General">一般名詞 (General)</option>
                        </TextField>
                    </Grid>
                    {/* IABカテゴリフィルタ */}
                    <Grid item xs={12} sm={4}>
                        <TextField
                            fullWidth
                            label="IABカテゴリ名"
                            variant="outlined"
                            value={iabCategoryFilter}
                            onChange={(e) => setIabCategoryFilter(e.target.value)}
                            placeholder="例: Food & Drink"
                            helperText="ノードのフィルタ (完全一致)"
                        />
                    </Grid>
                </Grid>

                {/* --- 結果表示エリア --- */}

                {/* エラーメッセージ */}
                {error && (
                    <Alert severity="error" sx={{mb: 2}}>
                        <Typography variant="body1" sx={{whiteSpace: 'pre-wrap'}}>
                            <strong>🚨 エラーが発生しました:</strong> {error}
                        </Typography>
                    </Alert>
                )}

                {/* Create 結果のメッセージ表示 */}
                <CreateResultDisplay status={createStatus}/>

                {/* グラフ描画エリア */}
                {graphData && (
                    <GraphVisualizationComponent
                        data={graphData}
                        isGraphPending={isGraphPending}
                        keyword={keyword}
                        maxDepth={maxDepth}
                        minScore={minScore} // 💡 追加
                        entityTypeFilter={entityTypeFilter} // 💡 追加
                        iabCategoryFilter={iabCategoryFilter} // 💡 追加
                    />
                )}

                {/* Analyze結果の表示 */}
                {analyzeData && (
                    <AnalyzeResultDisplay data={analyzeData}/>
                )}

                {/* Candidate結果の表示 */}
                {candidateData && (
                    <CandidateResultDisplay data={candidateData}/>
                )}

            </Paper>
        </Container>
    );
}


// ----------------------------------------
// Create 結果表示コンポーネント (変更なし)
// ----------------------------------------
interface CreateResultDisplayProps {
    status: 'idle' | 'success' | 'failure';
}

const CreateResultDisplay: React.FC<CreateResultDisplayProps> = ({status}) => {
    if (status === 'success') {
        return (
            <Alert severity="success" sx={{mb: 2}}>
                <Typography component="p" sx={{fontWeight: 'bold'}}>🎉 登録成功!</Typography>
                <Typography variant="body2">グラフ作成リクエストが FastAPI によって正常に処理されました。</Typography>
            </Alert>
        );
    }

    if (status === 'failure') {
        return (
            <Alert severity="error" sx={{mb: 2}}>
                <Typography component="p" sx={{fontWeight: 'bold'}}>❌ 登録失敗</Typography>
                <Typography variant="body2">詳細については、画面下部のエラーメッセージを確認してください。</Typography>
            </Alert>
        );
    }

    return null;
};


// ----------------------------------------
// Analyze結果表示コンポーネント (変更なし)
// ----------------------------------------

interface AnalyzeResultDisplayProps {
    data: AnalyzeKeywordsOutput;
}

interface AnalyzeResultDisplayProps {
    data: AnalyzeKeywordsOutput;
}

// 💡 エンティティタイプのスタイル関数
const getEntityTypeStyle = (type: string) => ({
    padding: '3px 8px',
    borderRadius: '4px',
    fontSize: '0.8em',
    fontWeight: 'bold',
    backgroundColor: type === 'Proper' ? '#fff9c4' : '#e3f2fd',
    color: type === 'Proper' ? '#f57f17' : '#1976d2',
});


const AnalyzeResultDisplay: React.FC<AnalyzeResultDisplayProps> = ({data}) => {
    if (!data.results || data.results.length === 0) {
        return (
            <Alert severity="warning" sx={{my: 2}}>
                🔍 キーワード「{data.seed_keyword}」に対する分析結果は見つかりませんでした。
            </Alert>
        );
    }

    return (
        <Paper elevation={1} sx={{
            p: 3,
            bgcolor: '#fff8e1',
            borderLeft: '5px solid #ff9800',
            my: 3
        }}>
            <Typography variant="h6" component="h3" sx={{mb: 2, fontWeight: 'bold', color: '#333'}}>
                📊 キーワード分析結果 (シードキーワード: {data.seed_keyword})
            </Typography>

            {/* 結果テーブル */}
            <Box sx={{overflowX: 'auto'}}>
                <table style={{width: '100%', minWidth: '600px', borderCollapse: 'collapse'}}>
                    <thead>
                    <tr style={{backgroundColor: '#f5f5f5'}}>
                        <th style={{
                            border: '1px solid #ddd',
                            padding: '8px',
                            textAlign: 'left',
                            width: '20%'
                        }}>キーワード
                        </th>
                        <th style={{
                            border: '1px solid #ddd',
                            padding: '8px',
                            textAlign: 'center',
                            width: '10%'
                        }}>スコア
                        </th>
                        <th style={{
                            border: '1px solid #ddd',
                            padding: '8px',
                            textAlign: 'center',
                            width: '15%'
                        }}>種別
                        </th>
                        <th style={{
                            border: '1px solid #ddd',
                            padding: '8px',
                            textAlign: 'left',
                            width: '55%'
                        }}>IABカテゴリ
                        </th>
                    </tr>
                    </thead>
                    <tbody>
                    {data.results
                        .sort((a, b) => b.score - a.score)
                        .map((item, index) => (
                            <tr key={item.keyword} style={{borderBottom: '1px solid #eee'}}>
                                <td style={{
                                    border: '1px solid #ddd',
                                    padding: '8px',
                                    fontWeight: 'bold',
                                    color: '#333'
                                }}>
                                    {index + 1}. {item.keyword}
                                </td>
                                <td style={{border: '1px solid #ddd', padding: '8px', textAlign: 'center'}}>
                                    <Chip
                                        label={item.score.toFixed(3)}
                                        size="small"
                                        sx={{
                                            bgcolor: item.score > 0.9 ? '#d32f2f' : '#ff9800',
                                            color: 'white',
                                            fontWeight: 'bold'
                                        }}
                                    />
                                </td>
                                <td style={{border: '1px solid #ddd', padding: '8px', textAlign: 'center'}}>
                                    {/* 💡 entity_type の表示 */}
                                    <span style={getEntityTypeStyle(item.entity_type)}>
                                            {item.entity_type === 'Proper' ? '固有名詞' : '一般名詞'}
                                        </span>
                                </td>
                                <td style={{border: '1px solid #ddd', padding: '8px'}}>
                                    {/* 💡 iab_categories の表示 */}
                                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                                        {item.iab_categories.map((cat, i) => (
                                            <Chip
                                                key={i}
                                                label={cat}
                                                size="small"
                                                sx={{
                                                    backgroundColor: '#f0f4c3', // ライトグリーン系で統一
                                                    color: '#333',
                                                    fontWeight: 'normal',
                                                    borderRadius: '4px'
                                                }}
                                            />
                                        ))}
                                    </Stack>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </Box>
        </Paper>
    );
};

// ----------------------------------------
// Candidate結果表示コンポーネント (変更なし)
// ----------------------------------------

interface CandidateResultDisplayProps {
    data: CandidateResponse;
}

const CandidateResultDisplay: React.FC<CandidateResultDisplayProps> = ({data}) => {
    if (!data.candidates || data.candidates.length === 0) {
        return (
            <Alert severity="info" sx={{my: 2}}>
                🔍 キーワード「{data.seed_keyword}」に対する候補は見つかりませんでした。
            </Alert>
        );
    }

    return (
        <Paper elevation={1} sx={{p: 3, bgcolor: '#e8f5e9', borderLeft: '5px solid #4caf50', my: 3}}>
            <Typography variant="h6" component="h3" sx={{mb: 2, fontWeight: 'bold', color: '#333'}}>
                ✅ Candidate 検索結果
            </Typography>

            <Box sx={{mb: 2, p: 1, bgcolor: '#f1f8e9', borderRadius: 1}}>
                <Typography variant="body1" sx={{color: '#333'}}>
                    リクエストキーワード: <Box component="span"
                                               sx={{fontWeight: 'bold'}}>{data.seed_keyword}</Box> (全 {data.candidates.length} 件)
                </Typography>
            </Box>

            <List disablePadding>
                {data.candidates.map((candidate, index) => (
                    <ListItem
                        key={candidate.videoId}
                        disableGutters
                        sx={{
                            py: 1,
                            borderBottom: '1px solid #eee',
                            alignItems: 'flex-start',
                            '&:last-child': {borderBottom: 'none'}
                        }}
                    >
                        <Grid container spacing={1}>
                            <Grid item xs={1}>
                                <Typography sx={{fontWeight: 'bold', color: 'primary.main', fontSize: '1.1em'}}>
                                    {index + 1}.
                                </Typography>
                            </Grid>
                            <Grid item xs={11}>
                                <Typography
                                    component="a"
                                    href={`https://www.youtube.com/watch?v=${candidate.videoId}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    sx={{
                                        color: 'info.main',
                                        textDecoration: 'none',
                                        '&:hover': {textDecoration: 'underline'}
                                    }}
                                >
                                    {candidate.snippet.title}
                                </Typography>
                            </Grid>
                        </Grid>
                    </ListItem>
                ))}
            </List>
        </Paper>
    );
};


// ----------------------------------------
// グラフ描画コンポーネント (maxDepth 表示を追加)
// ----------------------------------------

interface GraphVisualizationComponentProps {
    data: ShowGraphOutput;
    isGraphPending: boolean;
    keyword: string;
    maxDepth: number; // 💡 maxDepth を受け取る
    minScore: number;
    entityTypeFilter: string;
    iabCategoryFilter: string;
}

const GraphVisualizationComponent: React.FC<GraphVisualizationComponentProps> = ({
                                                                                     data,
                                                                                     isGraphPending,
                                                                                     keyword,
                                                                                     maxDepth,
                                                                                     minScore,
                                                                                     entityTypeFilter,
                                                                                     iabCategoryFilter
                                                                                 }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const [isVisLoaded, setIsVisLoaded] = useState(false);

    // vis.js の CDN ロード (変更なし)
    useEffect(() => {
        const scriptId = 'vis-js-script';
        const win = window as any;

        // 既存のライブラリチェックとCDNロードロジック...
        if (win.vis) {
            setIsVisLoaded(true);
            return;
        }

        if (!document.getElementById(scriptId)) {
            const script = document.createElement('script');
            script.src = 'https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.js';
            script.async = true;
            script.id = scriptId;
            script.onload = () => setIsVisLoaded(true);
            document.head.appendChild(script);

            const styleLink = document.createElement('link');
            styleLink.rel = 'stylesheet';
            styleLink.href = 'https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.css';
            document.head.appendChild(styleLink);
        }
    }, []);

    // グラフ描画ロジック (変更なし)
    useEffect(() => {
        // ★ 描画開始の厳密な条件チェック:
        // 1. visライブラリがロード済みであること
        // 2. 描画コンテナの参照が取れていること (DOMマウント完了)
        // 3. データが存在し、ノード数が0以上であること
        if (!isVisLoaded || !containerRef.current || data.nodes.length === 0) {
            return;
        }

        // 描画処理中 (Pending) の場合は、前の描画を維持して処理をスキップ
        if (isGraphPending) {
            return;
        }

        const vis = (window as any).vis;
        if (!vis) return;

        // --- データ変換 ---
        const normalizedKeyword = keyword.trim().toLowerCase();

        const nodes = new vis.DataSet(data.nodes.map((node: GraphNode) => {
            const normalizedNodeLabel = node.label.trim().toLowerCase();
            const nodeGroup = normalizedNodeLabel === normalizedKeyword ? 'seed' : 'related';

            // ツールチップにすべての属性を含める
            const nodeTitle = `
                <strong>Keyword:</strong> ${node.label}<br/>
                <strong>Type:</strong> ${node.entity_type || 'N/A'}<br/>
                <strong>IAB:</strong> ${(node.iab_categories || []).join(', ')}
            `;

            return {
                id: node.id,
                label: node.label,
                group: nodeGroup,
                title: nodeTitle,
            };
        }));

        const edges = new vis.DataSet(data.edges.map((edge: GraphEdge) => ({
            id: edge.id,
            from: edge.from_node,
            to: edge.to_node,
            value: edge.score * 10,
            title: `Score: ${edge.score.toFixed(3)}`
        })));

        const graphData = {nodes, edges};

        // --- 描画とクリーンアップ ---
        const options = {
            // ... (optionsは省略、そのまま適用)
            nodes: {
                shape: 'dot',
                size: 20,
                font: {size: 14, color: '#333'},
                borderWidth: 2
            },
            edges: {
                width: 2,
                arrows: 'to',
                color: {inherit: 'from'},
                smooth: {type: 'continuous'}
            },
            groups: {
                seed: {color: {background: '#FFC107', border: '#FF9800'}, size: 30},
                related: {color: {background: '#2196F3', border: '#1976D2'}},
            },
            physics: {
                enabled: true,
                barnesHut: {
                    gravitationalConstant: -2000,
                    centralGravity: 0.3,
                    springLength: 95,
                    springConstant: 0.04,
                    damping: 0.09,
                    avoidOverlap: 0.5
                },
                solver: 'barnesHut',
                stabilization: {enabled: true, iterations: 2500, updateInterval: 25}
            },
            height: '500px'
        };

        const network = new vis.Network(containerRef.current, graphData, options);

        // クリーンアップ関数を返す
        return () => {
            network.destroy();
        };

        // ★ 依存配列: 描画をトリガーするすべての状態を依存させる
    }, [isVisLoaded, data, isGraphPending, keyword, minScore, entityTypeFilter, iabCategoryFilter]);

    // グラフの描画を待機中の場合は CircularProgress を表示
    if (isGraphPending) {
        return (
            <Box sx={{display: 'flex', justifyContent: 'center', alignItems: 'center', height: '500px', my: 3}}>
                <CircularProgress/>
                <Typography variant="body1" sx={{
                    ml: 2,
                    color: 'text.secondary'
                }}>グラフデータをFastAPIから取得・描画中です...</Typography>
            </Box>
        );
    }

    // グラフデータがない場合の表示
    if (data.nodes.length === 0) {
        return (
            <Alert severity="info" sx={{my: 2}}>
                ℹ️ キーワード「{keyword}」（最大深さ: {maxDepth}）に関連するグラフデータが見つかりませんでした。
            </Alert>
        );
    }

    // グラフコンポーネント本体
    return (
        <Paper elevation={3} sx={{p: 3, my: 3}}>
            <Typography variant="h6" component="h3" sx={{mb: 1, fontWeight: 'bold'}}>
                📈 グラフ表示
            </Typography>
            <Typography variant="subtitle2" color="text.secondary" sx={{mb: 2}}>
                起点キーワード: **{keyword}** / 最大深さ: **{maxDepth}**
                <br/>
                フィルタ: スコア ≥ **{minScore}** | 種別: **{entityTypeFilter}** | IAB: **{iabCategoryFilter || 'なし'}**
                <br/>
                ({data.nodes.length} ノード / {data.edges.length} エッジ)
            </Typography>
            <Box
                // ★★★ 修正ポイント: ref={containerRef} を追加 ★★★
                ref={containerRef}
                sx={{
                    width: '100%',
                    height: '500px',
                    border: '1px solid #ddd',
                    borderRadius: '8px',
                    bgcolor: '#ffffff'
                }}
            />
            <Typography variant="caption" color="text.secondary" sx={{mt: 1, display: 'block'}}>
                ノードをドラッグしてレイアウトを変更できます。エッジの太さは関連度スコアを表します。
            </Typography>
        </Paper>
    );
};
